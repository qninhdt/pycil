"""Business failures; transport failures retain their infrastructure error types."""


class VocabularyError(Exception):
    usage = None


class InvalidHandleError(VocabularyError):
    pass


class InvalidResourceError(VocabularyError):
    pass


class InvalidOutputError(VocabularyError):
    pass


class WordCollisionError(VocabularyError):
    pass
