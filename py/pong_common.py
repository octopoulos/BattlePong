# coding: utf-8
# @author octopoulo <polluxyz@gmail.com>
# @version 2022-07-29

"""
Pong common
- code shared by server and client
"""

from math import cos, pi, sin, sqrt
from random import random
from typing import List

from Box2D import b2ChainShape, b2FixtureDef, b2PolygonShape, b2World
import pyuv

#
BALL_ANGLE = 0.3
BALL_SPEED_MAX = 20
BALL_SPEED_MED = 5
BALL_SPEED_MIN = 2
BALL_X = 16
BALL_Y = 16
OFFSET = 32
PADDLE_ACCEL = 0.4
PADDLE_X = 16
PADDLE_Y = 128
PHYSICS_FPS = 120
SCREEN_X = 1000
SCREEN_Y = 1000

# derived
BALL_SPEED_MAX2 = BALL_SPEED_MAX * BALL_SPEED_MAX
BALL_X2 = BALL_X // 2
BALL_Y2 = BALL_Y // 2
PADDLE_X2 = PADDLE_X // 2
PADDLE_Y2 = PADDLE_Y // 2
PHYSICS_STEP = 1 / PHYSICS_FPS
SCREEN_X2 = SCREEN_X // 2
SCREEN_Y2 = SCREEN_Y // 2


class Body:
	def __init__(self, name: str, id: int, x: float, y: float):
		self.name = name
		self.id = id
		self.alive = 1
		self.x = x
		self.y = y
		self.vx = 0
		self.vy = 0
		self.body = None

	def __str__(self):
		return f'<{self.name}: id={self.id} alive={self.alive} x={self.x} y={self.y} vx={self.vx} vy={self.vy}>'

	def Format(self) -> str:
		return f'{self.name[0]}{self.id}:{self.alive}:{self.x}:{self.y}:{self.vx}:{self.vy}\r\n'

	def Parse(self, items: List[str]) -> bool:
		if len(items) != 6: return False
		self.alive = int(items[1])
		self.x = float(items[2])
		self.y = float(items[3])
		self.vx = float(items[4])
		self.vy = float(items[5])
		return True


class Ball(Body):
	def __init__(self, id: int, x: float, y: float):
		super(Ball, self).__init__('Ball', id, x, y)


class Paddle(Body):
	def __init__(self, id: int, x: float, y: float, horiz: int):
		super(Paddle, self).__init__('Paddle', id, x, y)
		self.horiz = horiz


class Pong:
	def __init__(self):
		print('Pong')

		self.balls = [Ball(0, SCREEN_X2, SCREEN_Y2)]
		self.connected = False
		self.id = -1
		self.paddles = [
			Paddle(0, OFFSET           , SCREEN_Y2        , 0),
			Paddle(1, SCREEN_X - OFFSET, SCREEN_Y2        , 0),
			Paddle(2, SCREEN_X2        , OFFSET           , 1),
			Paddle(3, SCREEN_X2        , SCREEN_Y - OFFSET, 1),
		]

		self.world = b2World(gravity=(0, -10), doSleep=True)

		border = self.world.CreateStaticBody()
		border.CreateLoopFixture(vertices=[(5, -5), (5, 5), (-5, 5), (-5, -5)])

		self.ball = self.world.CreateDynamicBody(
			fixtures=b2FixtureDef(shape=b2PolygonShape(box=(BALL_X / 100, BALL_X / 100)), density=1.0, restitution=1.0),
			bullet=True,
			position=(0, 0))

	# NETWORK
	#########

	def Send(self, server: pyuv.TCP, data: bytes or str, log: bool=False):
		if not self.connected: return
		if log: print('>', data)
		if isinstance(data, str): data = data.encode()
		server.write(data)

	# GAME
	######

	def MoveBalls(self) -> int:
		dirty = 0

		# print(self.ball.position)
		self.world.Step(PHYSICS_STEP, 8, 3)

		for bid, ball in enumerate(self.balls):
			if not ball.alive: continue

			# 1) collision with walls
			flag = (1 << bid)
			ball.x += ball.vx
			ball.y += ball.vy

			if ball.x < BALL_X2:
				ball.x = BALL_X2
				ball.vx = abs(ball.vx)
				dirty |= flag
			elif ball.x > SCREEN_X - BALL_X2:
				ball.x = SCREEN_X - BALL_X2
				ball.vx = -abs(ball.vx)
				dirty |= flag

			if ball.y < BALL_Y2:
				ball.y = BALL_Y2
				ball.vy = abs(ball.vy)
				dirty |= flag
			elif ball.y > SCREEN_Y - BALL_Y2:
				ball.y = SCREEN_Y - BALL_Y2
				ball.vy = -abs(ball.vy)
				dirty |= flag

			# accelerate after a bounce
			if dirty:
				ball.vx *= 1.01
				ball.vy *= 1.01
				speed2 = ball.vx * ball.vx + ball.vy * ball.vy
				if speed2 > BALL_SPEED_MAX2:
					ispeed = BALL_SPEED_MAX / sqrt(speed2)
					ball.vx *= ispeed
					ball.vy *= ispeed

			#2) collision with paddles
			for pid, paddle in enumerate(self.paddles):
				if not paddle.alive: continue

				if paddle.horiz:
					x2 = PADDLE_Y2
					y2 = PADDLE_X2
				else:
					x2 = PADDLE_X2
					y2 = PADDLE_Y2

				if paddle.x + x2 <= ball.x - BALL_X2: continue
				if paddle.x - x2 >= ball.x + BALL_X2: continue
				if paddle.y + y2 <= ball.y - BALL_Y2: continue
				if paddle.y - y2 >= ball.y + BALL_Y2: continue

				print('BOOM', pid)
				self.ResetBall(ball)
				dirty |= flag

		return dirty

	def PrintBalls(self):
		for bid, ball in enumerate(self.balls):
			print(bid, ball)

	def ResetBall(self, ball: List):
		ball.alive = 1
		ball.x = SCREEN_X2
		ball.y = SCREEN_Y2

		# angle between 0 + eps and PI/2 - eps
		angle = BALL_ANGLE + (pi / 2 - BALL_ANGLE * 2) * random()
		speed = BALL_SPEED_MIN + random() * (BALL_SPEED_MED - BALL_SPEED_MIN)
		ball.vx = speed * cos(angle) * (1 if random() > 0.5 else -1)
		ball.vy = speed * sin(angle) * (1 if random() > 0.5 else -1)

	def ResetBalls(self):
		for ball in self.balls:
			self.ResetBall(ball)
