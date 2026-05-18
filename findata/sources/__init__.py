"""Data-source packages for the findata warehouse.

Each subpackage encapsulates an extract/transform pipeline for one upstream
source (news, market, corporate, sec, …). Schema definitions live in
:mod:`findata.models`; modules under :mod:`findata.sources` only contain
extraction/transform logic and the repositories that wrap them.
"""
