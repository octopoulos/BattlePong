# coding: utf-8
# @author octopoulo <polluxyz@gmail.com>
# @version 2022-08-01

"""
Renderer
"""

from typing import Tuple


class Renderer:
	def __init__(self, **kwargs):
		print('Renderer')
		self.name = 'null'
		self.screen = None

	def DrawCircle(self, x: float, y: float, radius: float, alpha: float, color: Tuple[int, int, int], drawLine: bool):
		pass

	def DrawLine(self, x: float, y: float, x2: float, y2: float, color: Tuple[int, int, int], width: int):
		pass

	def DrawQuad(self, x: float, y: float, rx: float, ry: float, alpha: float, color: Tuple[int, int, int]):
		pass
