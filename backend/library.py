"""Persistent project folders and atomic, recoverable library operations."""

import hashlib
import time
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProjectName(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Enter a project name.")
        return value


class LibraryAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=1, max_length=200)
    action: Literal["move", "trash", "restore"]
    project: str | None = Field(default=None, min_length=1, max_length=80)

    @model_validator(mode="after")
    def validate_action(self):
        if len(set(self.ids)) != len(self.ids):
            raise ValueError("Select each item only once.")
        if any(
            len(i) != 32 or any(c not in "0123456789abcdef" for c in i)
            for i in self.ids
        ):
            raise ValueError("Invalid track identifier.")
        if self.action == "move":
            self.project = (self.project or "").strip()
            if not self.project:
                raise ValueError("Choose a project.")
        elif self.project is not None:
            raise ValueError("Project is only used when moving tracks.")
        return self


def project_row(db, name, stamp):
    # Resolve the same folder even when capitalization differs.
    existing = db.execute(
        "SELECT id,name FROM projects WHERE name=? COLLATE NOCASE", (name,)
    ).fetchone()
    if existing:
        return dict(existing)
    identifier = hashlib.sha256(name.encode()).hexdigest()[:32]
    db.execute("INSERT INTO projects VALUES(?,?,?,?)", (identifier, name, stamp, stamp))
    return {"id": identifier, "name": name}


def routes(store):
    router = APIRouter()

    @router.get("/api/projects")
    def projects():
        with store.db() as db:
            return {
                "projects": [
                    dict(r)
                    for r in db.execute(
                        "SELECT id,name FROM projects ORDER BY name COLLATE NOCASE"
                    )
                ]
            }

    @router.post("/api/projects")
    def create_project(body: ProjectName):
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            result = project_row(db, body.name, int(time.time() * 1000))
            db.commit()
        return result

    @router.post("/api/library/actions")
    def apply_action(body: LibraryAction):
        stamp = int(time.time() * 1000)
        placeholders = ",".join("?" for _ in body.ids)
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                f"SELECT t.id,t.deleted_at,j.state FROM takes t JOIN generation_jobs j ON j.take_id=t.id WHERE t.id IN ({placeholders})",
                body.ids,
            ).fetchall()
            if len(rows) != len(body.ids):
                raise HTTPException(
                    404, "One or more tracks no longer exist. Nothing was changed."
                )
            if body.action == "trash":
                if any(
                    r["state"] in {"queued", "waiting-for-resource", "running"}
                    for r in rows
                ):
                    raise HTTPException(
                        409,
                        "Cancel or finish active generations before moving them to Trash. Nothing was changed.",
                    )
                db.execute(
                    f"UPDATE takes SET deleted_at=COALESCE(deleted_at,?),updated_at=? WHERE id IN ({placeholders})",
                    [stamp, stamp, *body.ids],
                )
            elif body.action == "restore":
                db.execute(
                    f"UPDATE takes SET deleted_at=NULL,updated_at=? WHERE id IN ({placeholders})",
                    [stamp, *body.ids],
                )
            else:
                if any(r["deleted_at"] is not None for r in rows):
                    raise HTTPException(
                        409, "Restore tracks from Trash before moving them."
                    )
                project = project_row(db, body.project, stamp)
                db.execute(
                    f"UPDATE takes SET project_id=?,updated_at=? WHERE id IN ({placeholders})",
                    [project["id"], stamp, *body.ids],
                )
            db.commit()
        return {
            "tracks": [
                t for t in store.rows(include_deleted=True) if t["id"] in body.ids
            ]
        }

    return router
