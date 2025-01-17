"""SQLAlchemy-based implementation of the repository protocol."""
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Literal, TypeVar

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .abc import AbstractRepository
from .exceptions import RepositoryConflictException, RepositoryException
from .filters import BeforeAfter, CollectionFilter, LimitOffset

if TYPE_CHECKING:
    from collections import abc
    from datetime import datetime

    from sqlalchemy import Select
    from sqlalchemy.engine import Result
    from sqlalchemy.ext.asyncio import AsyncSession

    from .. import orm
    from .types import FilterTypes

__all__ = [
    "SQLAlchemyRepository",
    "ModelT",
]

T = TypeVar("T")
ModelT = TypeVar("ModelT", bound="orm.Base")


@contextmanager
def wrap_sqlalchemy_exception() -> Any:
    """Do something within context to raise a `RepositoryException` chained
    from an original `SQLAlchemyError`.

        >>> try:
        ...     with wrap_sqlalchemy_exception():
        ...         raise SQLAlchemyError("Original Exception")
        ... except RepositoryException as exc:
        ...     print(f"caught repository exception from {type(exc.__context__)}")
        ...
        caught repository exception from <class 'sqlalchemy.exc.SQLAlchemyError'>
    """
    try:
        yield
    except IntegrityError as exc:
        raise RepositoryConflictException from exc
    except SQLAlchemyError as exc:
        raise RepositoryException(f"An exception occurred: {exc}") from exc


class SQLAlchemyRepository(AbstractRepository[ModelT]):
    """SQLAlchemy based implementation of the repository interface.

    Args:
        session: Session managing the unit-of-work for the operation.
        select_: To facilitate customization of the underlying select query.
    """

    model_type: type[ModelT]

    def __init__(
        self, session: "AsyncSession", select_: "Select[tuple[ModelT]] | None" = None
    ) -> None:
        super().__init__(session)
        self._select = select(self.model_type) if select_ is None else select_

    async def add(self, data: ModelT) -> ModelT:
        with wrap_sqlalchemy_exception():
            instance = await self._attach_to_session(data)
            await self.session.flush()
            await self.session.refresh(instance)
            self.session.expunge(instance)
            return instance

    async def delete(self, id_: Any) -> ModelT:
        with wrap_sqlalchemy_exception():
            instance = await self.get(id_)
            await self.session.delete(instance)
            await self.session.flush()
            self.session.expunge(instance)
            return instance

    async def get(self, id_: Any) -> ModelT:
        with wrap_sqlalchemy_exception():
            self._filter_select_by_kwargs(**{self.id_attribute: id_})
            instance = (await self._execute()).scalar_one_or_none()
            instance = self.check_not_found(instance)
            self.session.expunge(instance)
            return instance

    async def list(self, *filters: "FilterTypes", **kwargs: Any) -> list[ModelT]:
        for filter_ in filters:
            match filter_:
                case LimitOffset(limit, offset):
                    self._apply_limit_offset_pagination(limit, offset)
                case BeforeAfter(field_name, before, after):
                    self._filter_on_datetime_field(field_name, before, after)
                case CollectionFilter(field_name, values):
                    self._filter_in_collection(field_name, values)
        self._filter_select_by_kwargs(**kwargs)

        with wrap_sqlalchemy_exception():
            result = await self._execute()
            instances = list(result.scalars())
            for instance in instances:
                self.session.expunge(instance)
            return instances

    async def update(self, data: ModelT) -> ModelT:
        with wrap_sqlalchemy_exception():
            id_ = self.get_id_attribute_value(data)
            # this will raise for not found, and will put the item in the session
            await self.get(id_)
            # this will merge the inbound data to the instance we just put in the session
            instance = await self._attach_to_session(data, strategy="merge")
            await self.session.flush()
            await self.session.refresh(instance)
            self.session.expunge(instance)
            return instance

    async def upsert(self, data: ModelT) -> ModelT:
        with wrap_sqlalchemy_exception():
            instance = await self._attach_to_session(data, strategy="merge")
            await self.session.flush()
            await self.session.refresh(instance)
            self.session.expunge(instance)
            return instance

    @classmethod
    async def check_health(cls, session: "AsyncSession") -> bool:
        """Perform a health check on the database.

        Args:
            session: through which we runa check statement

        Returns:
            `True` if healthy.
        """
        return (  # type:ignore[no-any-return]  # pragma: no cover
            await session.execute(text("SELECT 1"))
        ).scalar_one() == 1

    # the following is all sqlalchemy implementation detail, and shouldn't be directly accessed

    def _apply_limit_offset_pagination(self, limit: int, offset: int) -> None:
        self._select = self._select.limit(limit).offset(offset)

    async def _attach_to_session(
        self, model: ModelT, strategy: Literal["add", "merge"] = "add"
    ) -> ModelT:
        """Attach detached instance to the session.

        Parameters
        ----------
        session: AsyncSession
            DB transaction.
        model : ModelT
            The instance to be attached to the session.
        strategy : Literal["add", "merge"]
            How the instance should be attached.

        Returns
        -------
        ModelT
        """
        match strategy:  # noqa: R503
            case "add":
                self.session.add(model)
                return model
            case "merge":
                return await self.session.merge(model)
            case _:
                raise ValueError("Unexpected value for `strategy`, must be `'add'` or `'merge'`")

    async def _execute(self) -> "Result[tuple[ModelT, ...]]":
        return await self.session.execute(self._select)

    def _filter_in_collection(self, field_name: str, values: "abc.Collection[Any]") -> None:
        if not values:
            return
        self._select = self._select.where(getattr(self.model_type, field_name).in_(values))

    def _filter_on_datetime_field(
        self, field_name: str, before: "datetime | None", after: "datetime | None"
    ) -> None:
        field = getattr(self.model_type, field_name)
        if before is not None:
            self._select = self._select.where(field < before)
        if after is not None:
            self._select = self._select.where(field > before)

    def _filter_select_by_kwargs(self, **kwargs: Any) -> None:
        for key, val in kwargs.items():
            self._select = self._select.where(getattr(self.model_type, key) == val)
