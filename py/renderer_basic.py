# coding: utf-8
# @author octopoulo <polluxyz@gmail.com>
# @version 2022-07-31

"""
Renderer Basic
"""

from math import cos, sin
from typing import Tuple

import pygame

from renderer import Renderer


class RendererBasic(Renderer):
	def __init__(self, **kwargs):
		super(RendererBasic, self).__init__(**kwargs)
		print('RendererBasic')
		self.name = 'basic'

	def DrawCircle(self, x: float, y: float, radius: float, alpha: float, color: Tuple[int, int, int]):
		pygame.draw.circle(self.screen, color, (x, y), radius)
		self.DrawLine(x, y, x + radius * cos(alpha), y + radius * sin(alpha), (255 - color[0], 255 - color[1], 255 - color[2]), 2)

	def DrawLine(self, x: float, y: float, x2: float, y2: float, color: Tuple[int, int, int], width: int):
		pygame.draw.line(self.screen, color, (x, y), (x2, y2), width)

	def DrawQuad(self, x: float, y: float, rx: float, ry: float, alpha: float, color: Tuple[int, int, int]):
		"""
		D ------ C      D ------ C
		| (x, y) |  =>  | (0, 0) |   => rotation => translation
		A ------ B      A ------ B

		A = (x, y) + (-rx, -ry) => A' = (x, y) + rot(-rx, -ry)
		B = (x, y) + ( rx, -ry) ...
		C = (x, y) + ( rx,  ry) ...
		D = (x, y) + (-rx,  ry) ...

		rot(rx, ry) => (rx * cosa - ry * sina, rx * sina + ry * cosa)
		"""
		if alpha == 0:
			pygame.draw.rect(self.screen, color, (x - rx, y - ry, rx * 2, ry * 2))
		# https://en.wikipedia.org/wiki/Rotation_matrix
		else:
			cosa = cos(alpha)
			sina = -sin(alpha)
			points = [
				(x + -rx * cosa - -ry * sina, y + -rx * sina + -ry * cosa),  # A
				(x +  rx * cosa - -ry * sina, y +  rx * sina + -ry * cosa),  # B
				(x +  rx * cosa -  ry * sina, y +  rx * sina +  ry * cosa),  # C
				(x + -rx * cosa -  ry * sina, y + -rx * sina +  ry * cosa),  # D
			]
			pygame.draw.polygon(self.screen, color, points)
