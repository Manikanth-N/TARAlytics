"""Shared pytest fixtures for TARAlytics tests."""
import pytest
import pandas as pd
import numpy as np
from tests.helpers import (
    synthetic_att_log as _att_log,
    synthetic_escx_log as _escx_log,
    minimal_signed_log as _signed_log,
    make_parsed_data,
)


def pytest_configure(config):
    config.addinivalue_line('markers', 'slow: long-running test (huge logs / soak)')


@pytest.fixture
def att_log_bytes():
    return _att_log()


@pytest.fixture
def escx_log_bytes():
    return _escx_log()


@pytest.fixture
def signed_log_bytes():
    return _signed_log()


@pytest.fixture
def parsed_data():
    return make_parsed_data()


@pytest.fixture
def gps_df():
    n = 20
    return pd.DataFrame({
        'TimeS': np.linspace(40.0, 60.0, n),
        'Lat':   np.linspace(-35.363, -35.364, n),
        'Lng':   np.linspace(149.165, 149.167, n),
        'Alt':   np.linspace(0.0, 50.0, n),
    })


@pytest.fixture
def sim2_df():
    n = 20
    return pd.DataFrame({
        'TimeS': np.linspace(40.0, 60.0, n),
        'PN':    np.linspace(0.0, 10.0, n),
        'PE':    np.linspace(0.0, 10.0, n),
        'PD':    np.linspace(0.0, -20.0, n),
    })
