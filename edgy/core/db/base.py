import decimal
from typing import Any, Dict, Optional, Pattern, Sequence, Union

import edgedb
from pydantic.fields import FieldInfo, Undefined

NO_DEFAULT = object()


class BaseField(FieldInfo):
    """
    The base field for all Edgy data model fields.
    """

    error_messages: Dict[str, str] = {}

    def __init__(
        self,
        *,
        default: Any = Undefined,
        title: Optional[str] = None,
        description: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        self.null: bool = kwargs.pop("null", False)
        if self.null and default is Undefined:
            default = None
        if default is not Undefined:
            self.default = default

        self.title = title
        self.description = description
        self.read_only: str = kwargs.pop("read_only", False)
        self.help_text: str = kwargs.pop("help_text", None)
        self.blank: bool = kwargs.pop("blank", False)
        self.pattern: Pattern = kwargs.pop("pattern", None)
        self.autoincrement: bool = kwargs.pop("autoincrement", False)
        self.primary_key: bool = kwargs.pop("primary_key", False)
        self.related_name: str = kwargs.pop("related_name", None)
        self.unique: bool = kwargs.pop("unique", False)
        self.index: bool = kwargs.pop("index", False)
        self.choices: Sequence = kwargs.pop("choices", None)
        self.owner: Any = kwargs.pop("owner", None)
        self.name: str = kwargs.pop("name", None)
        self.alias: str = kwargs.pop("name", None)
        self.max_digits: str = kwargs.pop("max_digits", None)
        self.decimal_places: str = kwargs.pop("decimal_places", None)
        self.regex: str = kwargs.pop("regex", None)
        self.min_length: Optional[Union[int, float, decimal.Decimal]] = kwargs.pop(
            "min_length", None
        )
        self.max_length: Optional[Union[int, float, decimal.Decimal]] = kwargs.pop(
            "max_length", None
        )
        self.minimum: Optional[Union[int, float, decimal.Decimal]] = kwargs.pop("minimum", None)
        self.maximum: Optional[Union[int, float, decimal.Decimal]] = kwargs.pop("maximum", None)
        self.exclusive_mininum: Optional[Union[int, float, decimal.Decimal]] = kwargs.pop(
            "exclusive_mininum", None
        )
        self.exclusive_maximum: Optional[Union[int, float, decimal.Decimal]] = kwargs.pop(
            "exclusive_maximum", None
        )
        self.multiple_of: Optional[Union[int, float, decimal.Decimal]] = kwargs.pop(
            "multiple_of", None
        )

        for name, value in kwargs.items():
            setattr(self, name, value)

        super().__init__(
            default=default,
            alias=self.alias,
            required=self.null,
            title=title,
            description=description,
            min_length=self.min_length,
            max_length=self.max_length,
            ge=self.minimum,
            le=self.maximum,
            gt=self.exclusive_mininum,
            lt=self.exclusive_maximum,
            multiple_of=self.multiple_of,
            max_digits=self.max_digits,
            decimal_places=self.decimal_places,
            regex=self.regex,
            **kwargs,
        )

    def get_alias(self) -> str:
        """
        Used to translate the model column names into database column tables.
        """
        return self.name

    def is_primary_key(self) -> bool:
        """
        Sets the autoincrement to True if the field is primary key.
        """
        if self.primary_key:
            self.autoincrement = True
        return False

    def has_default(self) -> bool:
        """Checks if the field has a default value set"""
        return bool(self.default is not None and self.default is not Undefined)

    def get_column(self, name: str) -> edgedb:
        """
        Returns the column type of the field being declared.
        """
        return self._type

    def expand_relationship(self, value: Any, child: Any, to_register: bool = True) -> Any:
        """
        Used to be overritten by any Link class.
        """

        return value

    def get_related_name(self) -> str:
        """Returns the related name used for reverse relations"""
        return ""