import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import AwareDatetime, BaseModel, Field
from sqlmodel import Session, select

from db.database import get_session
from db.models import CnsTest
from services.cns_baseline import baseline_deviation
from services.half_life_engine import as_utc
from services.i18n import Lang, get_lang, msg

router = APIRouter(prefix="/cns", tags=["cns"])

MAX_TAPS_IN_10_SECONDS = 200


class TestIn(BaseModel):
    tap_count_10s: int = Field(ge=0, le=MAX_TAPS_IN_10_SECONDS)
    timestamp: AwareDatetime | None = None


class TestOut(BaseModel):
    id: int
    timestamp: dt.datetime
    tap_count_10s: int
    baseline_dev_pct: float | None
    baseline_mean: float | None = None
    baseline_samples: int = 0

    @classmethod
    def of(cls, test: CnsTest, mean: float | None = None, samples: int = 0) -> "TestOut":
        return cls(id=test.id, timestamp=as_utc(test.timestamp), tap_count_10s=test.tap_count_10s,
                   baseline_dev_pct=test.baseline_dev_pct, baseline_mean=mean, baseline_samples=samples)


@router.post("/tests", status_code=201)
def record_test(body: TestIn, session: Session = Depends(get_session)) -> TestOut:
    moment = body.timestamp or dt.datetime.now(dt.timezone.utc)
    test = CnsTest(timestamp=moment, tap_count_10s=body.tap_count_10s)
    same_source = session.exec(select(CnsTest).where(CnsTest.source == test.source))
    deviation, mean, samples = baseline_deviation(body.tap_count_10s, moment, [(t.timestamp, t.tap_count_10s) for t in same_source])
    test.baseline_dev_pct = deviation
    session.add(test)
    session.commit()
    session.refresh(test)
    return TestOut.of(test, mean, samples)


@router.get("/tests")
def list_tests(limit: int = Query(30, ge=1, le=500), session: Session = Depends(get_session)) -> list[TestOut]:
    tests = session.exec(select(CnsTest).order_by(CnsTest.timestamp.desc()).limit(limit))
    return [TestOut.of(t) for t in tests]


@router.delete("/tests/{test_id}", status_code=204)
def delete_test(test_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> Response:
    test = session.get(CnsTest, test_id)
    if test is None:
        raise HTTPException(404, msg(lang, "http.tap_not_found"))
    session.delete(test)
    session.commit()
    return Response(status_code=204)
