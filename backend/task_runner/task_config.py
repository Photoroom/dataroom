class TaskConfig:
    def __init__(self, task_function, workers=1):
        self.name = task_function.__name__
        self.task_function = task_function
        self.workers = workers

    def __repr__(self):
        return f"<TaskConfig {self.name}>"

    def __str__(self):
        return self.__repr__()


class PeriodicTaskConfig(TaskConfig):
    def __init__(self, task_function, workers=1, interval_seconds=60):
        super().__init__(task_function, workers=workers)
        self.interval_seconds = interval_seconds


class QueuedTaskConfig(TaskConfig):
    def __init__(
        self,
        task_function,
        queue_feed_function,
        desired_queue_size=500,
        workers=1,
        retries=3,
        queue_feed_interval_seconds=1,
    ):
        """
        @param task_function: Function that processes items from the queue
        @param queue_feed_function: Function that returns items to be processed by the task
        @param desired_queue_size: Desired queue size
        @param workers: Number of workers to run the task
        @param retries: Number of retries for the task function
        @param queue_feed_interval_seconds: How often to check the queue size and feed new items to the task
        """
        super().__init__(task_function, workers=workers)
        self.queue_feed_function = queue_feed_function
        self.desired_queue_size = desired_queue_size
        self.retries = retries
        self.queue_feed_interval_seconds = queue_feed_interval_seconds
