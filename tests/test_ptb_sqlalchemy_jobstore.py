#!/usr/bin/env python
#
# A library containing community-based extension for the python-telegram-bot library
# Copyright (C) 2020-2023
# The ptbcontrib developers
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser Public License for more details.
#
# You should have received a copy of the GNU Lesser Public License
# along with this program.  If not, see [http://www.gnu.org/licenses/].
import datetime as dtm
import logging
import os
import platform

import apscheduler.triggers.interval
import pytest
from telegram.ext import CallbackContext, JobQueue

from ptbcontrib.ptb_sqlalchemy_jobstore import PTBSQLAlchemyJobStore  # noqa: E402


@pytest.fixture(scope="function")
async def jq(app):
    jq = JobQueue()
    jq.set_application(app)
    job_store = PTBSQLAlchemyJobStore(application=app, url="sqlite:///:memory:")
    jq.scheduler.add_jobstore(job_store)
    await jq.start()
    yield jq
    await jq.stop()


@pytest.fixture(scope="function")
def jobstore(jq):
    return jq.scheduler._jobstores["default"]


def dummy_job(ctx):
    # check if arg is instance of CallbackContext or not
    # to make sure it's properly serialized
    if not isinstance(ctx, CallbackContext):
        pytest.fail()


@pytest.mark.skipif(
    os.getenv("GITHUB_ACTIONS", False) and platform.system() in ["Windows", "Darwin"],
    reason="On Windows & MacOS precise timings are not accurate.",
)
class TestPTBJobstore:
    def test_default_jobstore_instance(self, jobstore):
        assert isinstance(jobstore, PTBSQLAlchemyJobStore)

    def test_next_runtime(self, jq, jobstore):
        jq.run_repeating(dummy_job, 10, first=0.1)
        assert jobstore.get_next_run_time().second == pytest.approx(
            dtm.datetime.now().second + 10, 1
        )

    def test_lookup_job(self, jq, jobstore):
        initial_job = jq.run_once(dummy_job, 1)
        job = jobstore.lookup_job(initial_job.id)
        assert job == initial_job.job
        assert job.name == initial_job.job.name
        assert job.args[0].callback is initial_job.callback is dummy_job

    def test_non_existent_job(self, jobstore):
        assert jobstore.lookup_job("foo") is None

    def test_get_all_jobs(self, jq, jobstore):
        j1 = jq.run_once(dummy_job, 1)
        j2 = jq.run_once(dummy_job, 2)
        j3 = jq.run_once(dummy_job, 3)
        jobs = jobstore.get_all_jobs()
        assert jobs == [j1.job, j2.job, j3.job]

    def test_operations_on_job(self, jq, jobstore):
        trigger = apscheduler.triggers.interval.IntervalTrigger(seconds=3)
        j1 = jq.run_once(dummy_job, 1)
        jq.scheduler.get_job(j1.job.id).pause()
        jq.scheduler.get_job(j1.job.id).resume()
        j_final = jq.scheduler.get_job(j1.job.id).reschedule(trigger)
        assert j_final.id == j1.job.id

    def test_remove_job(self, jq, jobstore):
        j1 = jq.run_once(dummy_job, 1)
        j2 = jq.run_once(dummy_job, 2)
        jobstore.remove_job(j1.id)
        assert jobstore.get_all_jobs() == [j2.job]
        jobstore.remove_job(j2.id)
        assert jobstore.get_all_jobs() == []

    def test_sqlite_warning(self, caplog, app):
        with caplog.at_level(logging.WARNING):
            PTBSQLAlchemyJobStore(app, url="sqlite:///:memory:")
        assert "Use of SQLite db is not supported" in caplog.text
