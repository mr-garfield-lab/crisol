def enqueue_job(queue, job):
    queue.append(job)
    return len(queue)

def pending_jobs(queue):
    return len(queue)
