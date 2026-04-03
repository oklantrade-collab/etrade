
from app.workers.scheduler import scheduler
import asyncio

async def check_jobs():
    print("=== SCHEDULER JOBS STATUS ===")
    for job in scheduler.get_jobs():
        print(f"ID: {job.id}, Next run: {job.next_run_time}, Trigger: {job.trigger}")

if __name__ == "__main__":
    # This won't work easily if we start a new scheduler...
    # But wait, if we start a script it won't see the ALREADY RUNNING scheduler jobs.
    pass
