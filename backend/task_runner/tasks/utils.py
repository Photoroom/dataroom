def chunks(iterable, chunk_size):
    if iterable is None:
        return
    for i in range(0, len(iterable), chunk_size):
        yield iterable[i : i + chunk_size]


class TaskResult:
    def __init__(self, result, next_kwargs=None):
        self.result = result
        if next_kwargs is None:
            next_kwargs = {}
        self.next_kwargs = next_kwargs
