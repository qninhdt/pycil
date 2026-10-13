"""Exercise bank failures with a stable application meaning."""


class QuestionArtifactBankChangedError(Exception):
    pass


class InvalidQuestionError(Exception):
    pass


class QuestionArtifactNotFoundError(Exception):
    pass


class UnsupportedQuestionFormatError(Exception):
    pass
