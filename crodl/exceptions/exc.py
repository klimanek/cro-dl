class DownloadError(Exception):
    pass


class DataEntryDoesNotExist(Exception):
    pass


class PlayerWrapperDoesNotExist(Exception):
    pass


class AudioUUIDDoesNotExist(Exception):
    pass


class ShowUUIDDoesNotExist(Exception):
    pass


class PageDoesNotExist(Exception):
    def __init__(self, message) -> None:
        self.message = message
        super().__init__(message)


class DataNotFound(KeyError):
    pass
