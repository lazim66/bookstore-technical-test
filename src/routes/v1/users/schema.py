from typing import Literal
from uuid import UUID

import bcrypt
from pydantic import BaseModel, Field, model_validator


class UserSignUpInput(BaseModel):
    email: str
    full_name: str = Field(min_length=1)
    password: str = Field(min_length=8)
    hashed_password: str | None = None

    @model_validator(mode="after")
    def hash_password(self):
        if self.password:
            self.hashed_password = bcrypt.hashpw(self.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        return self

    def model_dump(self, *args, **kwargs):
        exclude = kwargs.pop("exclude", set()) | {"password"}
        return super().model_dump(*args, **kwargs, exclude=exclude)


class UserLoginInput(BaseModel):
    email: str
    password: str


class UserUpdateInput(BaseModel):
    full_name: str | None = None
    password: str | None = Field(default=None, min_length=8)
    hashed_password: str | None = None

    @model_validator(mode="after")
    def hash_password(self):
        if self.password:
            self.hashed_password = bcrypt.hashpw(self.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        return self

    def model_dump(self, *args, **kwargs):
        exclude = kwargs.pop("exclude", set()) | {"password"}
        return super().model_dump(*args, **kwargs, exclude=exclude)


class AdminUserCreateInput(BaseModel):
    email: str
    full_name: str = Field(min_length=1)
    password: str = Field(min_length=8)
    role: Literal["customer", "admin"] = "customer"
    hashed_password: str | None = None

    @model_validator(mode="after")
    def hash_password(self):
        if self.password:
            self.hashed_password = bcrypt.hashpw(self.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        return self

    def model_dump(self, *args, **kwargs):
        exclude = kwargs.pop("exclude", set()) | {"password"}
        return super().model_dump(*args, **kwargs, exclude=exclude)


class RoleUpdateInput(BaseModel):
    role: Literal["customer", "admin"]


class UserOutput(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: Literal["customer", "admin"]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOutput
