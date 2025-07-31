import unittest
import json

from app.modules.gune.controller import GuneController


def test_index():
    gune_controller = GuneController()
    result = gune_controller.index()
    assert result == {'message': 'Hello, World!'}
