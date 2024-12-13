import logging
import time
import re
from typing import Optional
from datetime import datetime, timezone
import git
from queue import Queue
from threading import Thread
from llama_cpp import Llama
from queue import Empty
from typing import List

from .config import Config
from .github import GitHubClient
from .database import DatabaseManager
from .metrics import MetricsManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PRReviewer:
    def __init__(self):
        Config.validate()
        self.pr_queue = Queue()
        self.db = DatabaseManager()
        self.github = GitHubClient(
            token=Config.GITHUB_TOKEN,
            owner=Config.REPO_OWNER,
            repo=Config.REPO_NAME
        )
        
        # Initialize the model
        self.llm = Llama(
            model_path=Config.MODEL_PATH,
            verbose=False,
            n_ctx=2048,
            n_batch=4,
            n_threads=2
        )
        
        # Initialize git repo
        self.repo = git.Repo(Config.REPO_PATH)

        # Initialize metrics
        self.metrics = MetricsManager()

    def get_pr_diff(self, pr_number: int) -> Optional[str]:
        """Get only the modified lines from a diff for a specific PR."""
        logger.info("Getting PR Diff")
        try:
            self.repo.git.checkout('master')

            self.repo.git.fetch('origin', f'pull/{pr_number}/head')

            diff = self.repo.git.diff('master', 'FETCH_HEAD', unified=3, minimal=True, no_prefix=True, diff_filter='M')

            processed_diff = self.process_diff_content(diff)
            
            # Return to master branch
            self.repo.git.checkout('master')
            
            return processed_diff
        except git.GitCommandError as e:
            logger.error(f"Git error while getting diff: {e}")
            return None
        finally:
            # Cleanup: delete the PR branch
            try:
                self.repo.git.branch('-D', f"pr-{pr_number}")
            except git.GitCommandError:
                pass

    def process_diff_content(self, diff: str) -> str:
        """Process the diff to extract relevant changed lines with minimal context."""
        logger.info("Processing diff content")
        processed_chunks = []
        current_file = None
        
        print("Raw diff:", diff[:500])  # First 500 chars to see format
        SKIP_EXTENSIONS = {'.lock', '.json', '.md', '.txt', '.yaml', '.yml', '.yaml', '.mod', '.sum'}
        SKIP_PATHS = {'tests/', 'docs/', 'vendor/', 'migrations/'}
        # Split diff into lines
        lines = diff.split('\n')
        
        for line in lines:
            # Check for file header
            if line.startswith('diff --git'):
                if current_file:
                    processed_chunks.append('')  # Add spacing between files
                file_match = re.search(r'b/(.+)$', line)
                if not file_match:
                    continue

                filepath = file_match.group(1)

                if any(path in filepath for path in SKIP_PATHS):
                    current_file = None
                    continue

                if any(ext in filepath for ext in SKIP_EXTENSIONS):
                    current_file = None
                    continue

                if current_file:
                    processed_chunks.append(f"File: {current_file}")

                current_file = filepath
                processed_chunks.append(f"File: {current_file}")
                continue
                
            # Skip if we're in a file we don't want to process
            if current_file is None:
                continue

            # Skip index lines and file markers
            if (line.startswith('index ') or 
                line.startswith('+++') or 
                line.startswith('---')):
                continue
                
            # Include hunk headers (showing line numbers) and modified lines
            if (line.startswith('+') or 
                line.startswith('-')):
                processed_chunks.append(line)

            # Include hunk headers but simplified
            elif line.startswith('@@ '):
                processed_chunks.append('@@@ Changes @@@')
                
            # Include one line of context if it's meaningful
            elif line.strip() and not line.startswith((' ', '\t')):
                processed_chunks.append(' ' + line)

        result = '\n'.join(processed_chunks)
        
        diff_length = len(result.split())
        if diff_length > 500:
            logger.warning(f"Large diff detected: {diff_length} words")
            # Take only first part of each file's changes
            chunks = result.split('File: ')
            processed = ['File: ' + chunk[:1000] + '\n[truncated...]' 
                for chunk in chunks[1:]]
            return '\n'.join(processed)

        return result

    def analyze_diff(self, diff: str) -> str:
        """Analyze the diff using the LLM."""
        logger.info("Analyzing Diff")

        start_time = time.time()
        all_analyses = []

        try:
            file_chunks = diff.split('\nFile: ')

            for chunk in file_chunks:
                if not chunk.strip():
                    continue

                chunk_tokens = len(chunk.split())

                if chunk_tokens > 3000:
                    sub_analyses = self.analyze_large_chunk(chunk)
                    all_analyses.extend(sub_analyses)
                else:
                    analysis = self.analyze_single_chunk(chunk)
                    if analysis:
                        all_analyses.append(analysis)

            final_analysis = self.combine_analyses(all_analyses)

            processing_time = time.time() - start_time
            self.metrics.record_llm_metrics(
                pr_number=self.current_pr_number,
                input_tokens=sum(len(a.split()) for a in all_analyses),
                output_tokens=len(final_analysis.split()),
                processing_time=processing_time
            )
        
            return final_analysis

        except Exception as e:
            self.metrics.record_llm_metrics(
                    pr_number=self.current_pr_number,
                    input_tokens=input_tokens,
                    output_tokens=0,
                    processing_time=time.time() - start_time,
                    error_message=str(e)
            )
            raise

    def analyze_single_chunk(self, chunk: str) -> Optional[str]:
        """Analyze a single chunk of diff that fits in context window."""
        logger.info("Analyzing Chunk")
        prompt = f"""As a senior developer specializing in database performance, review this section of a pull request:

        {chunk}

        Focus your analysis specifically on the changed lines and their immediate impact on:
        1. Query efficiency and N+1 problems
        2. Index usage
        3. Transaction boundaries
        4. Race conditions
        5. Cache invalidation
        6. Query plan impacts

        Format your response in a concise bullet-point format focusing only on issues found, if any."""

        try:
            response = self.llm(
                prompt,
                max_tokens=1024,  # Smaller response for each chunk
                temperature=0.7,
                stop=["Human:", "Assistant:"]
            )
            return response['choices'][0]['text'].strip()
        except Exception as e:
            logger.warning(f"Failed to analyze chunk: {e}")
            return None

    def analyze_large_chunk(self, chunk: str) -> List[str]:
        """Break down large chunks into smaller pieces."""
        logger.info("Analyzing Large Chunk")
        analyses = []
    
        # Split by change blocks (@@@ Changes @@@)
        change_blocks = chunk.split('@@@ Changes @@@')
    
        current_block = []
        current_tokens = 0
    
        for block in change_blocks:
            block_tokens = len(block.split())
        
            if current_tokens + block_tokens > 3000:
                # Analyze current accumulated blocks
                if current_block:
                    combined = '@@@ Changes @@@'.join(current_block)
                    analysis = self.analyze_single_chunk(combined)
                    if analysis:
                        analyses.append(analysis)
                current_block = [block]
                current_tokens = block_tokens
            else:
                current_block.append(block)
                current_tokens += block_tokens
    
        # Analyze any remaining blocks
        if current_block:
            combined = '@@@ Changes @@@'.join(current_block)
            analysis = self.analyze_single_chunk(combined)
            if analysis:
                analyses.append(analysis)
    
        return analyses

    def combine_analyses(self, analyses: List[str]) -> str:
        """Combine individual analyses into a coherent review."""
        logger.info("Combine Analyses")

        if not analyses:
            return "No significant database-related issues found in the changes."
    
        combined_analyses = {'\n\n'.join(analyses)}

        # Create summary prompt with all individual analyses
        summary_prompt = f"""Synthesize these code review findings into a cohesive summary:
            {combined_analyses}
            Focus on:
            1. Common themes across files
            2. Most critical issues
            3. Overall recommendations
            Format with sections:
            - Summary
            - Critical Issues
            - Recommendations"""

        try:
            response = self.llm(
                summary_prompt,
                max_tokens=2048,
                temperature=0.7,
                stop=["Human:", "Assistant:"]
            )
            return response['choices'][0]['text'].strip()
        except Exception as e:
            logger.error(f"Failed to combine analyses: {e}")
            # Fall back to simple concatenation
            return "\n\n=====\n\n".join(analyses)

    def process_pull_request(self, pr: dict):
        """Process a single pull request."""
        logger.info("Process PR")

        try:
            pr_number = pr['number']
            self.current_pr_number = pr_number

            metric_id = self.metrics.start_pr_processing(pr_number)
            
            # Skip if already processed
            if self.db.is_pr_processed(pr_number):
                self.metrics.end_pr_processing(metric_id, 'skipped')
                return

            # Get and analyze diff
            diff = self.get_pr_diff(pr_number)
            if not diff:
                self.metrics.end_pr_processing(metric_id, 'failed', error_message='Failed to get diff')
                logger.error(f"Failed to get diff for PR #{pr_number}")
                return

            diff_size = len(diff)

            review = self.analyze_diff(diff)
            
            # Submit review
            if self.github.submit_review_comment(pr_number, review):
                self.db.mark_pr_processed(pr_number)
                self.db.add_review_history(pr_number, review)
                self.metrics.end_pr_processing(metric_id, 'completed', diff_size=diff_size)
                logger.info(f"Successfully processed PR #{pr_number}")
            else:
                self.metrics.end_pr_processing(metric_id, 'failed', diff_size=diff_size, error_message='Failed to submit review')
                logger.error(f"Failed to submit review for PR #{pr_number}")

        except Exception as e:
            self.metrics.end_pr_processing(metric_id, 'failed', error_message=str(e))
            logger.error(f"Error processing PR #{pr.get('number', 'unknown')}: {e}")

    def check_new_prs(self):
        """Check for new PRs and add them to the queue."""
        logger.info("Check for new PRs")
        prs = self.github.get_pull_requests()
        for pr in prs:
            if not self.db.is_pr_processed(pr['number']):
                self.pr_queue.put(pr)
                logger.info(f"Queued PR #{pr['number']} for processing")

    def process_queue(self):
        """Process PRs from the queue."""
        logger.info("Process PRs from queue")

        while True:
            try:
                pr = self.pr_queue.get(timeout=1)
                self.process_pull_request(pr)
                self.pr_queue.task_done()
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Error in queue processing: {e}")
                time.sleep(1)

    def run(self):
        """Run the PR reviewer service."""
        logger.info("Starting PR Reviewer service")
        
        # Start PR processing thread
        processor_thread = Thread(target=self.process_queue, daemon=True)
        processor_thread.start()
        
        # Main loop for checking new PRs
        while True:
            try:
                self.check_new_prs()
                if datetime.now().minute == 0:
                    self.metrics.update_daily_metrics()
                time.sleep(Config.CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(Config.CHECK_INTERVAL)

def main():
    reviewer = PRReviewer()
    reviewer.run()

if __name__ == "__main__":
    main()
