"""Pervallam SQL API"""

import datetime
#from typing import Annotated
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
#from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
SQLALCHEMY_DATABASE_URL = "sqlite:///./sql_app.db"
# SQLALCHEMY_DATABASE_URL = "postgresql://user:password@postgresserver/db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

#security = HTTPBasic()

class Job(BaseModel):
    """A job"""
    id: int | None = None  # TODO ensure API always returns this
    url: str | None = None  # TODO ensure it has this on inital POST
    dler: str | None = None
    fname: str | None = None
    status: str | None = None
    started: datetime.datetime | None = None
    updated: datetime.datetime | None = None
    class Config:
        orm_mode = True

class Dler(BaseModel):
    """Simple model temporarily for assign"""
    dler: str

def get_db():
    """Get a db connection"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

#import flask
#import flask_sqlalchemy

# Create the Flask application and the Flask-SQLAlchemy object.
#app = flask.Flask(__name__)
#app.config.from_envvar('PVSQLAPI_SETTINGS', silent=True)
#db = flask_sqlalchemy.SQLAlchemy(app)


class JobTable(Base):
    """Task table in database"""
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    url = Column(String(256), nullable=False)
    dler = Column(String(16))
    fname = Column(String(64))
    status = Column(String(8), default='new')
    started = Column(DateTime)
    updated = Column(DateTime)

Base.metadata.create_all(bind=engine)


@app.get('/jobs/')
def joblist(filt: str = None, db: Session = Depends(get_db)) -> list[Job]:
    """Get some or a subset of jobs"""
    if filt == 'unassigned':
        return db.query(JobTable).filter(JobTable.status == 'new').all()
    if filt == 'active':
        return db.query(JobTable).filter(~JobTable.status.in_(['ended', 'stopped'])).all()
    return db.query(JobTable).all()

@app.get('/jobs/{job_id}')
def onejob(job_id: int, db: Session = Depends(get_db)) -> Job:
    """Return details of one job"""
    return db.query(JobTable).get(job_id)


@app.post('/jobs/', status_code=201)
def newjob(job: Job, db: Session = Depends(get_db)) -> Job:
    """Create a new job"""
    db_job = JobTable(url = job.url)
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job

# TODO redo for posting the assignee
@app.post('/jobs/{job_id}/assign', status_code=204)
#def assign(job_id: int, credentials: Annotated[HTTPBasicCredentials, Depends(security)], db: Session = Depends(get_db)) -> None:
def assign(job_id: int, dler: Dler, db: Session = Depends(get_db)) -> None:
    """Assign a job to a worker"""
    db_job = db.query(JobTable).get(job_id)
    if db_job.status != 'new':
        raise HTTPException(status_code=409, detail="Cannot be assigned")
    db_job.status = 'assigned'
    #db_job.dler = credentials.username
    db_job.dler = dler.dler
    db.commit()
    db.refresh(db_job)

@app.post('/jobs/{job_id}/stop', status_code=204)
def stop(job_id:int, db: Session = Depends(get_db)) -> None:
    """Request that a job be stopped before it has ended"""
    db_job = db.query(JobTable).get(job_id)
    if db_job.status == 'new':
        db_job.status = 'stopped'
        db.commit()
        db.refresh(db_job)
        return
    if db_job.status not in ['assigned', 'running']:
        raise HTTPException(status_code=409, detail="Cannot be stopped")
    db_job.status = 'stopreq'
    db.commit()
    db.refresh(db_job)

@app.patch('/jobs/{job_id}')
def patch(job_id: int, job: Job, db: Session = Depends(get_db)) -> Job:
    """Worker updates a job with current status"""
    db_job = db.query(JobTable).get(job_id)
    update_data = job.dict(exclude_unset=True)
    #db_job.copy(update=update_data)
    for field, value in update_data.items():
        if value:
            setattr(db_job, field, value)
    db.commit()
    db.refresh(db_job)
    return db_job


#get_db().create_all()


#if __name__ == '__main__':
#    app.run()
