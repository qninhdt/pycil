"""Isolated SDK measurements without global providers or exporters."""

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from pycil import observability


@pytest.fixture
def operation_metrics(monkeypatch):
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    monkeypatch.setattr(
        observability,
        "_operation_duration",
        provider.get_meter("pycil.operation").create_histogram(
            "pycil.operation.duration", unit="s"
        ),
    )

    def points():
        data = reader.get_metrics_data()
        assert data is not None
        values = [
            point
            for resource in data.resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
            for point in metric.data.data_points
        ]
        assert all(set(point.attributes) == {"operation", "outcome"} for point in values)
        assert all(point.sum >= 0 for point in values)
        assert "private" not in str(data)
        return values

    try:
        yield points
    finally:
        provider.shutdown()
