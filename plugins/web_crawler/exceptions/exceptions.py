class ApplicationException(Exception):
    """애플리케이션 전용 예외의 최상위 클래스."""


class CollectionException(ApplicationException):
    """수집 파이프라인 실행에 실패했을 때 발생."""


class ExportException(ApplicationException):
    """결과 파일을 저장하지 못했을 때 발생."""
