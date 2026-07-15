from abc import ABC, abstractmethod
from app.models import NormalizedResult


class BaseSource(ABC):
    # Department this source serves (appliances, medical, office, it,
    # janitorial, hardware, furniture). None = relevant to every department;
    # such sources are always queried regardless of the department filter.
    department: str | None = None

    @abstractmethod
    async def search(self, query: str, limit: int) -> tuple[list[NormalizedResult], str | None]:
        """
        Search for items matching query.
        Returns (results, error_message). error_message is None on success.
        """
        ...
