import threading
import time
import logging
from sqlalchemy import select
from backend.app.database import get_sync_db
from backend.app.models.models import Job
from backend.app.services.export_runner import run_export_job
from backend.app.services.trash import purge_expired

logger = logging.getLogger("clippy.worker")

class JobWorker:
    TRASH_SWEEP_INTERVAL_S = 3600

    def __init__(self):
        self._stop_event = threading.Event()
        self._thread = None
        self._next_trash_sweep = 0.0

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="JobWorkerThread")
        self._thread.start()
        logger.info("Job worker thread started")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
            logger.info("Job worker thread stopped")

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._poll_jobs()
            except Exception as e:
                logger.error(f"Error in job worker: {e}", exc_info=True)
            try:
                self._sweep_trash()
            except Exception as e:
                logger.error(f"Error sweeping trash: {e}", exc_info=True)
            time.sleep(1.0)

    def _sweep_trash(self):
        now = time.monotonic()
        if now < self._next_trash_sweep:
            return
        self._next_trash_sweep = now + self.TRASH_SWEEP_INTERVAL_S
        with get_sync_db() as db:
            purge_expired(db)

    def _poll_jobs(self):
        with get_sync_db() as db:
            job = db.execute(
                # only job kinds we can run: an unknown "pending" job at the head of the queue would block everything
                select(Job).where(Job.state == "pending", Job.kind == "export")
                .order_by(Job.created_at.asc()).limit(1)
            ).scalar_one_or_none()

            if not job:
                return

            job_id = job.id

        try:
            run_export_job(job_id)
        except Exception as e:
            # an exception outside the ffmpeg loop would leave the job "running" forever
            logger.error(f"Export job {job_id} crashed: {e}", exc_info=True)
            with get_sync_db() as db:
                job = db.get(Job, job_id)
                if job and job.state in ("pending", "running"):
                    job.state = "error"
                    job.error = str(e)[-500:]
                    db.commit()

worker = JobWorker()
