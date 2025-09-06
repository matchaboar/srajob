from pydantic import BaseModel


class JobListing(BaseModel):
    job_title: str
    url: str
    location: str | None
    remote: bool | None
