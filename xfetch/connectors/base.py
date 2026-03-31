from abc import ABC, abstractmethod

from xfetch.models import NormalizedDocument


class BaseConnector(ABC):
    @abstractmethod
    def can_handle(self, url: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def fetch(self, url: str) -> NormalizedDocument:
        raise NotImplementedError
