class ProcessWaitError(Exception):
    """
    Raised when there is a pr
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        try:
            self.exitcode = kwargs["exitcode"]
        except KeyError:
            pass
