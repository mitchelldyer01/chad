# src/reviewer.py
import logging
import time
from typing import Optional
import git
from queue import Queue
from threading import Thread
from llama_cpp import Llama

from .config import Config
from .github import GitHubClient
from .database import DatabaseManager

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
            n_ctx=512,
            n_batch=4,
            n_threads=2
        )
        
        # Initialize git repo
        self.repo = git.Repo(Config.REPO_PATH)

        # Initialize metrics
        self.metrics = MetricsManager()

    def get_pr_diff(self, pr_number: int) -> Optional[str]:
        """Get the diff for a specific PR."""
        try:
            remote_ref = f"pull/{pr_number}/head:pr-{pr_number}"
            self.repo.git.fetch('origin', remote_ref)
            self.repo.git.checkout(f"pr-{pr_number}")
            
            diff = self.repo.git.diff('master')
            
            # Return to master branch
            self.repo.git.checkout('master')
            
            return diff
        except git.GitCommandError as e:
            logger.error(f"Git error while getting diff: {e}")
            return None
        finally:
            # Cleanup: delete the PR branch
            try:
                self.repo.git.branch('-D', f"pr-{pr_number}")
            except git.GitCommandError:
                pass

    def analyze_diff(self, diff: str) -> str:
        """Analyze the diff using the LLM."""

        start_time = time.time()

        try:
            prompt = f"""As a senior developer specializing in database performance, review this pull request diff:

            {diff}

            Focus your analysis on:
            1. Query efficiency and N+1 problems
            2. Index usage and missing indexes
            3. Transaction boundaries and isolation levels
            4. Connection pool usage
            5. Race conditions
            6. Cache invalidation issues
            7. Database migration risks
            8. Query plan impacts

            Format your response with these sections:
            - Summary
            - Critical Issues (if any)
            - Performance Recommendations
            - Best Practices
            - Migration Considerations (if applicable)

            Keep your response constructive and actionable."""

            input_tokens = len(prompt.split())

            response = self.llm(
                prompt,
                max_tokens=2048,
                temperature=0.7,
                stop=["Human:", "Assistant:"]
            )

            processing_time = time.time() - start_time
            output_tokens = len(response['choices'][0]['text'].split())

            self.metrics.record_llm_metrics(
                pr_number=self.current_pr_number,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                processing_time=processing_time
            )
        
            return response['choices'][0]['text'].strip()

        except Exception as e:
            self.metrics.record_llm_metrics(
                    pr_number=self.current_pr_number,
                    input_tokens=input_tokens,
                    output_tokens=0,
                    processing_time=time.time() - start_time,
                    error_message=str(e)
            )
            raise

    def process_pull_request(self, pr: dict):
        """Process a single pull request."""
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
        prs = self.github.get_pull_requests()
        for pr in prs:
            if not self.db.is_pr_processed(pr['number']):
                self.pr_queue.put(pr)
                logger.info(f"Queued PR #{pr['number']} for processing")

    def process_queue(self):
        """Process PRs from the queue."""
        while True:
            try:
                pr = self.pr_queue.get(timeout=1)
                self.process_pull_request(pr)
                self.pr_queue.task_done()
            except Queue.Empty:
                time.sleep(1)
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
