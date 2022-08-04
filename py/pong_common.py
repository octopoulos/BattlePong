# coding: utf-8
# @author octopoulo <polluxyz@gmail.com>
# @version 2022-08-02

"""
Pong common
- code shared by server and client
"""

from itertools import chain
from math import cos, pi, sin
from random import random
import struct
from time import time

from Box2D import b2CircleShape, b2Contact, b2ContactListener, b2FixtureDef, b2PolygonShape, b2World
import pyuv

from common import DefaultInt

VERSION = '2022-08-02'

# game
BALL_ANGLE      = 0.3       # min starting throw angle
BALL_ORBIT      = 1.5       # starting orbit
BALL_SPEED_MAX  = 20
BALL_SPEED_MED  = 15
BALL_SPEED_MIN  = 7
BALL_SPEED_STOP = 1.2
BALL_X          = 0.2
BALL_Y          = 0.2
PADDLE_ACCEL    = 0.2
PADDLE_BOUNCE   = 0.15
PADDLE_FAR2     = 3         # stay a bit away from the ball when stuck behind
PADDLE_FORCE    = 50        # max moving force
PADDLE_GAP      = 0.73      # space between border and paddle
PADDLE_HIT      = 0.15      # impulse angle
PADDLE_IMPULSE  = 0.2       # impulse speed
PADDLE_NEAR2    = 1.5       # maybe hit distance
PADDLE_X        = 0.16
PADDLE_Y        = 1.28
PHYSICS_FPS     = 120
PHYSICS_IT_MAX  = 1000
PHYSICS_IT_POS  = 3         # number of position iterations
PHYSICS_IT_VEL  = 8         # number of velocity iterations
SUN_RADIUS      = 0.2
WALL_SUBDIVIDE  = 7
WALL_THICKNESS  = 0.08
ZONE_X2         = 6
ZONE_Y2         = 6

# derived
BALL_SPEED_MAX2  = BALL_SPEED_MAX * BALL_SPEED_MAX
BALL_SPEED_STOP2 = BALL_SPEED_STOP * BALL_SPEED_STOP
BALL_X2          = BALL_X / 2
BALL_Y2          = BALL_Y / 2
PADDLE_X2        = PADDLE_X / 2
PADDLE_Y2        = PADDLE_Y / 2
PHYSICS_STEP     = 1 / PHYSICS_FPS

# hits
HIT_BALL_BALL     = 1 << 0
HIT_BALL_PADDLE   = 1 << 1
HIT_BALL_WALL     = 1 << 2
HIT_PADDLE_PADDLE = 1 << 3
HIT_PADDLE_WALL   = 1 << 4


class Body:
	structFmt  = 'xBBBffffff'
	structSize = struct.calcsize(structFmt)

	def __init__(self, name: str, id: int, x: float, y: float, angle: float):
		self.letter    = ord(name[0])
		self.name      = name
		self.id        = id
		self.alive     = 1
		self.angle     = angle            # interpolated angle
		self.angle0    = angle            # initial angle
		self.angle1    = angle            # prev angle
		self.flag      = 0
		self.parentId  = -1               # hit by ... -1 if nothing
		self.position  = (x, y)           # interpolated position
		self.position0 = (x, y)           # initial position
		self.position1 = (x, y)           # prev position
		self.body      = None

	def __str__(self):
		body = self.body
		pos  = body.position
		vel  = body.linearVelocity
		return f'<{self.name}: id={self.id} alive={self.alive} pos=({pos[0]},{pos[1]}) vel=({vel[0]},{vel[1]}) rot={body.angle} rotVel={body.angularVelocity}>'

	def Format(self) -> bytes:
		body = self.body
		pos  = body.position
		vel  = body.linearVelocity
		return struct.pack(Body.structFmt, self.letter, self.id, self.alive, pos[0], pos[1], vel[0], vel[1], body.angle, body.angularVelocity)

	def Parse(self, message: bytes) -> bool:
		body = self.body
		_, _, self.alive, posx, posy, velx, vely, body.angle, body.angularVelocity = struct.unpack(Body.structFmt, message)
		body.position       = (posx, posy)
		body.linearVelocity = (velx, vely)
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
		body.position        = (self.position0[0], self.position0[1])


class Ball(Body):
	structFmt  = 'xBBBffffffb'
	structSize = struct.calcsize(structFmt)

	def __init__(self, world: b2World, id: int, x: float, y: float, angle: float):
		super(Ball, self).__init__('Ball', id, x, y, angle)

		self.body = world.CreateDynamicBody(
			allowSleep     = False,
			angularDamping = 0.03,
			bullet         = True,
			fixtures       = b2FixtureDef(shape=b2CircleShape(radius=BALL_X2), density=1.0, friction=0.2, restitution=0.95),
			userData       = ['B', id, self],
		)

	def Format(self) -> bytes:
		body = self.body
		pos  = body.position
		vel  = body.linearVelocity
		return struct.pack(Ball.structFmt, self.letter, self.id, self.alive, pos[0], pos[1], vel[0], vel[1], body.angle, body.angularVelocity, self.parentId)

	def Parse(self, message: bytes) -> bool:
		body = self.body
		_, _, self.alive, posx, posy, velx, vely, body.angle, body.angularVelocity, self.parentId = struct.unpack(Ball.structFmt, message)
		body.position       = (posx, posy)
		body.linearVelocity = (velx, vely)
		return True


class Paddle(Body):
	structFmt  = 'xBBBffffffih'
	structSize = struct.calcsize(structFmt)

	def __init__(self, world: b2World, id: int, x: float, y: float, angle: float):
		super(Paddle, self).__init__('Paddle', id, x, y, angle)
		self.parentId = id

		self.buttons = 0                  # buttons can be used for prediction
		self.health  = 1

		self.body = world.CreateDynamicBody(
			allowSleep     = False,
			angularDamping = 0.1,
			bullet         = True,
			fixtures       = b2FixtureDef(shape=b2PolygonShape(box=(PADDLE_X2, PADDLE_Y2)), density=2.0, friction=0.3, restitution=0.3),
			userData       = ['P', id, self],
		)

	def Alive(self, alive: int):
		if alive != self.alive:
			self.alive = alive
			self.body.angularDamping          = 0.1 if alive else 0.0
			self.body.fixtures[0].restitution = 0.3 if alive else 0.9

	def Format(self) -> bytes:
		body = self.body
		pos  = body.position
		vel  = body.linearVelocity
		return struct.pack(Paddle.structFmt, self.letter, self.id, self.alive, pos[0], pos[1], vel[0], vel[1], body.angle, body.angularVelocity, self.buttons, self.health)

	def Parse(self, message: bytes) -> bool:
		body = self.body
		_, _, alive, posx, posy, velx, vely, body.angle, body.angularVelocity, self.buttons, self.health = struct.unpack(Paddle.structFmt, message)
		self.Alive(alive)
		body.position       = (posx, posy)
		body.linearVelocity = (velx, vely)
		return True


class Pong(b2ContactListener):
	def __init__(self, **kwargs):
		super(Pong, self).__init__()
		print('Pong', kwargs)

		# options
		self.host      = str(kwargs.get('host'))
		self.port      = DefaultInt(kwargs.get('port'), 1234)
		self.reconnect = DefaultInt(kwargs.get('reconnect'), 3)

		self.connected   = False
		self.dirtyBall   = 0              # which balls must be sent via network (flag)
		self.dirtyPaddle = 0              # which paddles must be sent via network (flag)
		self.dirtyWall   = 0              # wall was hit => paddle id flag
		self.doneFrame   = 0
		self.frame       = 0
		self.hitFlag     = 0
		self.id          = -1
		self.ideltas     = [0] * 8        # previous [pframe - iframe] deltas
		self.iframe      = -1             # frame where prev Physics was simulated
		self.pframe      = -1             # frame where current Physics was simulated
		self.sdelta      = 0              # average of ideltas
		self.start       = time()
		self.walls       = [255] * 16     # wall energy

		self.world                   = b2World(gravity=(0, 0), doSleep=True)
		self.world.contactListener   = self
		self.world.warmStarting      = True
		self.world.continuousPhysics = True
		self.world.subStepping       = True

		# create bodies
		self.numDiv = WALL_SUBDIVIDE
		self.wall   = self.world.CreateStaticBody(userData=['W', 0, None])
		self.CreateWalls()

		self.sun = self.world.CreateStaticBody(
			fixtures = b2FixtureDef(shape=b2CircleShape(radius=SUN_RADIUS), density=5.0),
			position = (0, 0),
			userData = ['S', 0, None],
		)

		self.paddles = [
			Paddle(self.world, 0, 0                    , -ZONE_Y2 + PADDLE_GAP, pi / 2),
			Paddle(self.world, 1, -ZONE_X2 + PADDLE_GAP, 0                    , 0     ),
			Paddle(self.world, 2, 0                    , ZONE_Y2 - PADDLE_GAP , pi / 2),
			Paddle(self.world, 3, ZONE_X2 - PADDLE_GAP , 0                    , 0     ),
		]
		self.balls = [Ball(self.world, 0, 0, 0, 0)]

	# NETWORK
	#########

	def Send(self, server: pyuv.TCP, data: bytes or str, log: bool = False):
		if not self.connected: return
		if log: print('>', data)
		if isinstance(data, str): data = data.encode()
		server.write(data)

	# GAME
	######

	def AddBall(self, number: int = 1):
		for _ in range(number):
			ball = Ball(self.world, len(self.balls), 0, 0, 0)
			self.balls.append(ball)
			self.ResetBall(ball)

	def BeginContact(self, contact: b2Contact):
		self.Contact(contact, False)

	def CalculateHealth(self, pid: int, makeDirty: bool):
		health = 0
		start = pid * self.numDiv
		for i in range(self.numDiv): health += (1 if self.walls[start + i] > 0 else 0)

		paddle        = self.paddles[pid]
		paddle.health = health
		if health == 0: paddle.Alive(0)
		if makeDirty: self.dirtyPaddle |= (1 << pid)

	def Contact(self, contact: b2Contact, isEnd: bool):
		bodyA         = contact.fixtureA.body
		bodyB         = contact.fixtureB.body
		nameA, idA, A = bodyA.userData
		nameB, idB, B = bodyB.userData

		if nameA == 'B':
			self.dirtyBall |= (1 << idA)
			if nameB == 'B':
				if not isEnd: self.hitFlag |= HIT_BALL_BALL
				self.dirtyBall |= (1 << idB)
			elif nameB == 'P':
				if not isEnd: self.hitFlag |= HIT_BALL_PADDLE
				self.dirtyPaddle |= (1 << idB)
				A.flag |= (1 << idB)
				A.parentId = idB
			elif nameB == 'S':
				self.dirtyBall |= (1 << idB)
				A.flag |= 128
			elif nameB == 'W':
				self.ContactBallWall(A, contact.childIndexB, isEnd)
		#
		elif nameA == 'P':
			self.dirtyPaddle |= (1 << idA)
			if nameB == 'B':
				if not isEnd: self.hitFlag |= HIT_BALL_PADDLE
				self.dirtyBall |= (1 << idB)
				B.flag |= (1 << idA)
				B.parentId = idA
			elif nameB == 'P':
				if not isEnd: self.hitFlag |= HIT_PADDLE_PADDLE
				self.dirtyPaddle |= (1 << idB)
			elif nameB == 'W':
				if not isEnd: self.hitFlag |= HIT_PADDLE_WALL
		#
		elif nameA == 'S':
			if nameB == 'B':
				self.dirtyBall |= (1 << idA)
				B.flag |= 128
		#
		elif nameA == 'W':
			if nameB == 'B':
				self.ContactBallWall(B, contact.childIndexA, isEnd)
			elif nameB == 'P':
				if not isEnd: self.hitFlag |= HIT_PADDLE_WALL
				self.dirtyPaddle |= (1 << idB)

	def ContactBallWall(self, ball: Ball, childId: int, isEnd: bool):
		wallId = childId // self.numDiv
		if not isEnd:
			self.hitFlag |= HIT_BALL_WALL
			if (health := self.walls[childId]) > 0:
				# speed >= 400 => destroyed in 1 hit
				vel    = ball.body.linearVelocity
				speed2 = (vel[0] * vel[0] + vel[1] * vel[1])

				# reduce self damage
				if ball.parentId == wallId: speed2 *= 0.5

				self.walls[childId] = max(int(health - speed2 * 0.64), 0)
				self.CalculateHealth(wallId, True)

				# vampire
				if ball.parentId >= 0 and wallId != ball.parentId:
					self.RepairWall(ball.parentId, health - self.walls[childId])

				self.dirtyWall |= (1 << childId)

		self.dirtyBall |= (1 << ball.id)
		if ball.parentId >= 0 and self.walls[childId] > 0: ball.parentId = -1

	def CreateWalls(self):
		numDiv   = self.numDiv
		segments = [(ZONE_X2, -ZONE_X2), (-ZONE_X2, -ZONE_X2), (-ZONE_X2, ZONE_X2), (ZONE_X2, ZONE_X2)]

		if numDiv > 0:
			vertices = []
			for i in range(4):
				x, y   = segments[i]
				x2, y2 = segments[(i + 1) % 4]
				dx     = (x2 - x) / numDiv
				dy     = (y2 - y) / numDiv
				for j in range(numDiv): vertices.append((x + dx * j, y + dy * j))
		else:
			vertices = segments

		if len(self.wall.fixtures): self.wall.DestroyFixture(self.wall.fixtures[0])
		self.wall.CreateLoopFixture(vertices=vertices)
		self.walls = [255] * (len(vertices) + 1)

	def DeleteBall(self):
		if len(self.balls) > 1:
			ball = self.balls.pop()
			self.world.DestroyBody(ball.body)

	def EndContact(self, contact: b2Contact):
		self.Contact(contact, True)

	def Interpolate(self, interpolate: bool):
		if not interpolate or self.sdelta < 1:
			for obj in chain(self.balls, self.paddles):
				body         = obj.body
				obj.angle    = body.angle
				obj.position = body.position
		else:
			id = self.frame - self.pframe

			if id == 0:
				for obj in chain(self.balls, self.paddles):
					obj.angle    = obj.angle1
					obj.position = obj.position1
			else:
				# hack to make sure we avoid duplicate frames
				# 0.9 => 0.95 => 0.975 ...
				if id >= self.sdelta:
					id -= 1
					v = (id / self.sdelta + 1) / 2

					while id >= self.sdelta:
						v = (v + 1) / 2
						id -= 1
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

		numDelta = len(self.ideltas)
		for i in range(numDelta - 1): self.ideltas[i] = self.ideltas[i + 1]
		self.ideltas[numDelta - 1] = self.pframe - self.iframe
		self.sdelta = int(sum(self.ideltas) / numDelta + 0.5)

		self.iframe = self.pframe

	def NewGame(self, numDiv: int = 0):
		if numDiv > 0: self.numDiv = numDiv
		if len(self.walls) != self.numDiv: self.CreateWalls()

		for obj in chain(self.balls, self.paddles): obj.Reset()
		self.ResetBalls()

		for i in range(len(self.walls)): self.walls[i] = 255

		for pid, paddle in enumerate(self.paddles):
			self.CalculateHealth(pid, False)
			paddle.Alive(1)

		self.doneFrame = 0
		self.frame     = 0
		self.iframe    = -1
		self.pframe    = -1
		self.start     = time()

	def Physics(self):
		# sun gravity
		for ball in self.balls:
			body = ball.body
			pos  = body.position
			grav = 0.02 / (pos[0] * pos[0] + pos[1] * pos[1] + 0.1)

			# hit sun
			if ball.flag & 128: grav = -grav * 15 - 10

			force = (-pos[0] * grav, -pos[1] * grav)
			body.ApplyForceToCenter(force, True)

			# too slow ball? => accelerate
			vel    = ball.body.linearVelocity
			speed2 = (vel[0] * vel[0] + vel[1] * vel[1])
			if speed2 < BALL_SPEED_STOP2 * BALL_SPEED_STOP2: self.ResetBall(ball, False)

		# move paddles
		for paddle in self.paddles:
			body = paddle.body
			ppos = body.position

			# move back towards original position
			if paddle.alive:
				deltaX = (paddle.position0[0] - ppos[0]) if paddle.angle0 == 0 else 0
				deltaY = (paddle.position0[1] - ppos[1]) if paddle.angle0 != 0 else 0
				force  = (
					-body.linearVelocity[0] * 1 + deltaX * 5,
					-body.linearVelocity[1] * 1 + deltaY * 5
				)
				body.ApplyTorque((paddle.angle0 - body.angle) * 3 - body.angularVelocity * 0.35, True)

			# dead => move a bit towards one of the 1st ball
			else:
				ball  = self.balls[0]
				bpos  = ball.body.position
				delta = (bpos[0] - ppos[0], bpos[1] - ppos[1])
				grav  = 1 / (delta[0] * delta[0] + delta[1] * delta[1] + 8)
				force = (delta[0] * grav, delta[1] * grav)

			body.ApplyForceToCenter(force, True)

		# run solver
		self.world.Step(PHYSICS_STEP, PHYSICS_IT_VEL, PHYSICS_IT_POS)
		self.world.ClearForces()
		self.pframe = self.frame

	def PhysicsLoop(self, interpolate: bool = False):
		elapsed   = time() - self.start
		wantFrame = elapsed * PHYSICS_FPS

		for ball in self.balls: ball.flag = 0

		self.dirtyBall   = 0
		self.hitFlag     = 0
		self.dirtyPaddle = 0
		self.dirtyWall   = 0

		if self.doneFrame < wantFrame:
			if interpolate:
				self.InterpolateStore()

			for _ in range(PHYSICS_IT_MAX):
				self.Physics()
				self.doneFrame += 1
				if self.doneFrame >= wantFrame: break

		self.Interpolate(interpolate)

	def RepairWall(self, pid: int, health: float):
		start = pid * self.numDiv

		for _ in range(self.numDiv):
			bestId    = -1
			bestScore = 255
			for i in range(self.numDiv):
				if (wall := self.walls[start + i]) > 0 and wall < bestScore:
					bestId    = i + start
					bestScore = wall

			if bestId < 0: break

			wall               = self.walls[bestId]
			self.walls[bestId] = min(wall + health, 255)

			health -= (self.walls[bestId] - wall)
			if health <= 0: break

		self.CalculateHealth(pid, True)

	def ResetBall(self, ball: Ball, recenter: bool = True):
		# angle between 0 + eps and PI/2 - eps
		angle = BALL_ANGLE + (pi / 2 - BALL_ANGLE * 2) * random()
		speed = BALL_SPEED_MIN + random() * (BALL_SPEED_MED - BALL_SPEED_MIN)

		if recenter:
			alpha         = ball.id * 2 * pi / len(self.balls)
			body          = ball.body
			body.position = (BALL_ORBIT * cos(alpha), BALL_ORBIT * sin(alpha))

		body                = ball.body
		ball.alive          = 1
		body.linearVelocity = (speed * cos(angle) * (1 if random() > 0.5 else -1), speed * sin(angle) * (1 if random() > 0.5 else -1))

		self.dirtyBall |= (1 << ball.id)

	def ResetBalls(self, recenter: bool = True):
		for ball in self.balls: self.ResetBall(ball, recenter)

	def SetBalls(self, count: int):
		while len(self.balls) > count: self.DeleteBall()
		while len(self.balls) < count: self.AddBall()
