# coding: utf-8
# @author octopoulo <polluxyz@gmail.com>
# @version 2022-07-31

"""
Pong common
- code shared by server and client
"""

from itertools import chain
from math import cos, pi, sin
from random import random
from time import time
from typing import List

from Box2D import b2CircleShape, b2ContactListener, b2FixtureDef, b2PolygonShape, b2World
import pyuv

from common import *

VERSION = '2022-07-31'

# game
BALL_ANGLE     = 0.3
BALL_SPEED_MAX = 20
BALL_SPEED_MED = 15
BALL_SPEED_MIN = 7
BALL_X         = 0.16
BALL_Y         = 0.16
PADDLE_ACCEL   = 0.5
PADDLE_BOUNCE  = 0.15
PADDLE_GAP     = 0.32
PADDLE_X       = 0.16
PADDLE_Y       = 1.28
PHYSICS_FPS    = 120
PHYSICS_IT_POS = 3
PHYSICS_IT_VEL = 8
SCALE          = 100
SCREEN_X       = 1000
SCREEN_Y       = 1000

# derived
BALL_SPEED_MAX2 = BALL_SPEED_MAX * BALL_SPEED_MAX
BALL_X2         = BALL_X / 2
BALL_Y2         = BALL_Y / 2
PADDLE_X2       = PADDLE_X / 2
PADDLE_Y2       = PADDLE_Y / 2
PHYSICS_STEP    = 1 / PHYSICS_FPS
SCREEN_X2       = SCREEN_X // 2
SCREEN_Y2       = SCREEN_Y // 2
ZONE_X2         = SCREEN_X2 / SCALE
ZONE_Y2         = SCREEN_Y2 / SCALE


class Body:
	def __init__(self, name: str, id: int, x: float, y: float):
		self.name      = name
		self.id        = id
		self.alive     = 1
		self.angle     = 0                # interpolated angle
		self.angle0    = 0                # initial angle
		self.angle1    = 0                # prev angle
		self.position  = (0, 0)           # interpolated position
		self.position0 = (x, y)           # initial position
		self.position1 = (0, 0)           # prev position
		self.body      = None

	def __str__(self):
		body = self.body
		return f'<{self.name}: id={self.id} alive={self.alive} pos=({body.position[0]},{body.position[1]}) vel=({body.linearVelocity[0]},{body.linearVelocity[1]}) rot={body.angle} rotVel={body.angularVelocity}>'

	def Format(self) -> str:
		body = self.body
		return f'{self.name[0]}{self.id}:{self.alive}:{body.position[0]}:{body.position[1]}:{body.linearVelocity[0]}:{body.linearVelocity[1]}:{body.angle}:{body.angularVelocity}\r\n'

	def Parse(self, items: List[str]) -> bool:
		if len(items) != 8: return False
		body                 = self.body
		self.alive           = DefaultInt(items[1], 1)
		body.position        = (float(items[2], float(items[3])))
		body.linearVelocity  = (float(items[4], float(items[5])))
		body.angle           = float(items[6])
		body.angularVelocity = float(items[7])
		return True

	def Reset(self):
		self.angle     = self.angle0
		self.angle1    = self.angle0
		self.position  = (self.position0[0], self.position0[1])
		self.position1 = (self.position0[0], self.position0[1])

		body                 = self.body
		body.angle           = self.angle
		body.angularVelocity = 0.0
		body.linearVelocity  = (0.0, 0.0)
		body.position        = (self.position[0], self.position[1])


class Ball(Body):
	def __init__(self, world: b2World, id: int, x: float, y: float):
		super(Ball, self).__init__('Ball', id, x, y)

		self.body = world.CreateDynamicBody(
			allowSleep = False,
			bullet     = True,
			# fixtures   = b2FixtureDef(shape=b2PolygonShape(box=(BALL_X2, BALL_X2)), density=1.0, restitution=1.0),
			fixtures   = b2FixtureDef(shape=b2CircleShape(radius=BALL_X2), density=1.0, restitution=1.01),
		)


class Paddle(Body):
	def __init__(self, world: b2World, id: int, x: float, y: float, angle: float):
		super(Paddle, self).__init__('Paddle', id, x, y)

		self.angle = angle
		self.body  = world.CreateDynamicBody(
			allowSleep      = False,
			bullet          = True,
			# fixedRotation = True,
			fixtures        = b2FixtureDef(shape=b2PolygonShape(box=(PADDLE_X2, PADDLE_Y2)), density=1.2, friction=0.3, restitution=1.0),
		)


class Pong(b2ContactListener):
	def __init__(self, **kwargs):
		super(Pong, self).__init__()
		print('Pong', kwargs)

		# options
		self.host      = str(kwargs.get('host'))
		self.port      = DefaultInt(kwargs.get('port'), 1234)
		self.reconnect = DefaultInt(kwargs.get('reconnect'), 3)

		self.connected = False
		self.doneFrame = 0
		self.frame     = 0
		self.id        = -1
		self.ideltas   = [0] * 4  # previous [pframe - iframe] deltas
		self.iframe    = -1       # frame where prev Physics was simulated
		self.pframe    = -1       # frame where current Physics was simulated
		self.sdelta    = 0        # average of ideltas
		self.start     = time()

		self.world                   = b2World(gravity=(0, 0), doSleep=True)
		self.world.contactListener   = self
		self.world.warmStarting      = True
		self.world.continuousPhysics = True
		self.world.subStepping       = True

		border = self.world.CreateStaticBody()
		border.CreateLoopFixture(vertices=[(5, -5), (5, 5), (-5, 5), (-5, -5)])

		# create bodies
		gap            = PADDLE_GAP
		self.balls     = [Ball(self.world, 0, 0, 0)]
		self.paddles   = [
			Paddle(self.world, 0, -ZONE_X2 + gap, 0             , 0     ),
			Paddle(self.world, 1, ZONE_X2 - gap , 0             , 0     ),
			Paddle(self.world, 2, 0             , -ZONE_Y2 + gap, pi / 2),
			Paddle(self.world, 3, 0             , ZONE_Y2 - gap , pi / 2),
		]

	# NETWORK
	#########

	def Send(self, server: pyuv.TCP, data: bytes or str, log: bool = False):
		if not self.connected: return
		if log: print('>', data)
		if isinstance(data, str): data = data.encode()
		server.write(data)

	# GAME
	######

	def AddBall(self):
		ball = Ball(self.world, 0, 0, 0)
		self.balls.append(ball)
		self.ResetBall(ball)

	def Interpolate(self, interpolate: bool):
		if not interpolate or self.sdelta < 1:
			for obj in chain(self.balls, self.paddles):
				body         = obj.body
				obj.angle    = body.angle
				obj.position = body.position
		else:
			id = self.frame - self.pframe
			# hack to make sure we avoid duplicate frames
			if id == self.sdelta: self.sdelta += 1

			if id == 0:
				for obj in chain(self.balls, self.paddles):
					obj.angle    = obj.angle1
					obj.position = obj.position1
			else:
				v = id / self.sdelta
				u = 1 - v

				for obj in chain(self.balls, self.paddles):
					body         = obj.body
					obj.angle    = obj.angle1 * u + body.angle * v
					obj.position = (
						obj.position1[0] * u + body.position[0] * v,
						obj.position1[1] * u + body.position[1] * v
					)

	def InterpolateStore(self):
		for obj in chain(self.balls, self.paddles):
			body          = obj.body
			obj.angle1    = body.angle
			obj.position1 = (body.position[0], body.position[1])

		for i in range(3):
			self.ideltas[i] = self.ideltas[i + 1]
		self.ideltas[3] = self.pframe - self.iframe
		self.sdelta = int(sum(self.ideltas) / 4 + 0.5)

		self.iframe = self.pframe

	def NewGame(self):
		for obj in chain(self.balls, self.paddles):
			obj.Reset()

		self.ResetBalls()
		self.PrintBalls()

		self.doneFrame = 0
		self.frame     = 0
		self.iframe    = -1
		self.pframe    = -1
		self.start     = time()

	def Physics(self):
		self.world.Step(PHYSICS_STEP, PHYSICS_IT_VEL, PHYSICS_IT_POS)
		self.world.ClearForces()
		self.pframe = self.frame

	def PhysicsLoop(self, interpolate: bool = False):
		elapsed   = time() - self.start
		wantFrame = elapsed * PHYSICS_FPS

		if self.doneFrame < wantFrame:
			if interpolate:
				self.InterpolateStore()

			while True:
				self.Physics()
				self.doneFrame += 1
				if self.doneFrame >= wantFrame: break

		self.Interpolate(interpolate)

	def PrintBalls(self):
		for bid, ball in enumerate(self.balls):
			print(bid, ball)

	def ResetBall(self, ball: List):
		# angle between 0 + eps and PI/2 - eps
		angle   = BALL_ANGLE + (pi / 2 - BALL_ANGLE * 2) * random()
		speed   = BALL_SPEED_MIN + random() * (BALL_SPEED_MED - BALL_SPEED_MIN)

		body                = ball.body
		ball.alive          = 1
		body.linearVelocity = (speed * cos(angle) * (1 if random() > 0.5 else -1), speed * sin(angle) * (1 if random() > 0.5 else -1))

	def ResetBalls(self):
		for ball in self.balls:
			self.ResetBall(ball)
