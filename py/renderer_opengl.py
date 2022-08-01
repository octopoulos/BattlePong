# coding: utf-8
# @author octopoulo <polluxyz@gmail.com>
# @version 2022-07-30

"""
Renderer OpenGL
"""

from typing import Tuple

from renderer import Renderer


class RendererOpenGL(Renderer):
	def __init__(self, **kwargs):
		super(RendererOpenGL, self).__init__(**kwargs)
		print('RendererOpenGL')
		self.name = 'opengl'

	def DrawCircle(self, x: float, y: float, radius: float, alpha: float, color: Tuple[int, int, int]):
		pass

	def DrawLine(self, x: float, y: float, x2: float, y2: float, color: Tuple[int, int, int], width: int):
		pass

	def DrawQuad(self, x: float, y: float, rx: float, ry: float, alpha: float, color: Tuple[int, int, int]):
		pass
