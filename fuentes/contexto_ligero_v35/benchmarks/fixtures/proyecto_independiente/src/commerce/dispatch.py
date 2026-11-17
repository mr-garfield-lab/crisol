from .queue import enqueue_job
from .receipt import write_receipt

def dispatch_job(queue, job):
    enqueue_job(queue, job)
    return write_receipt(job)
