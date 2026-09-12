"""Bounded image work; completed artifacts survive a failed sibling request."""
import asyncio
import os

DEFAULT_CONCURRENCY = 8


def configured_concurrency():
    # This is an app resource limit, not a claimed OpenAI provider maximum.
    value=int(os.environ.get('SOUND_VISION_IMAGE_CONCURRENCY',DEFAULT_CONCURRENCY))
    if not 1<=value<=32:
        raise ValueError('SOUND_VISION_IMAGE_CONCURRENCY must be between 1 and 32.')
    return value


async def image_batch(account, items, operation, phase, label):
    items=list(items)
    if not items:return []
    results=[None]*len(items);pending=iter(enumerate(items));failures=[]
    completed=0;active=0
    def progress():phase(f'{label} · {completed}/{len(items)} complete · {active} active')
    async def worker():
        nonlocal completed,active
        while not failures:
            try:index,item=next(pending)
            except StopIteration:return
            active+=1;progress()
            try:
                results[index]=await operation(item)
                completed+=1
            except Exception as error:
                failures.append(error)
            finally:
                active-=1;progress()
    tasks=[asyncio.create_task(worker()) for _ in range(min(getattr(account,'image_concurrency',DEFAULT_CONCURRENCY),len(items)))]
    try:
        await asyncio.gather(*tasks)
    finally:
        # Explicit cancellation stops the batch. A normal image failure lets
        # other in-flight requests finish and save their results first.
        for task in tasks:
            if not task.done():task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
    if failures:
        error=failures[0]
        raise RuntimeError(f'{label}: {str(error).strip() or type(error).__name__} Completed images are retained; remaining images were not started.') from error
    return results
