# coding: utf-8
# @author octopoulo <polluxyz@gmail.com>
# @version 2022-07-31

"""
Pong client
"""

import os
import signal
from time import time

import pygame
import pyuv

from pong_common import *
from renderer_basic import Renderer, RendererBasic
from renderer_opengl import RendererOpenGL


PADDLE_COLORS = (
	(0  , 255, 0  ),
	(255, 0  , 0  ),
	(0  , 0  , 255),
	(128, 128, 128),
)

PY_PATH    = os.path.dirname(__file__)
PONG_PATH  = os.path.abspath(PY_PATH + '/..')
SOUND_PATH = os.path.join(PONG_PATH, 'sound')

SOUND_SOURCES = [
	'269718__michorvath__ping-pong-ball-hit.wav',
]


class PongClient(Pong):
	def __init__(self, **kwargs):
		super(PongClient, self).__init__(**kwargs)
		print('PongClient', kwargs)

		# options
		self.interpolate = DefaultInt(kwargs.get('interpolate'), 0)
		self.rendererClass = {
			'basic': RendererBasic,
			'opengl': RendererOpenGL,
		}[kwargs.get('renderer')]

		self.client     = None                                   # type: pyuv.TCP
		self.clock      = pygame.time.Clock()
		self.grab       = True
		self.hit        = 0
		self.keys       = {}
		self.lastKey    = ''
		self.mouseAbs   = [SCREEN_X2, SCREEN_Y2]
		self.mouseAccel = [0, 0]
		self.mousePos   = [SCREEN_X2, SCREEN_Y2]
		self.mousePrev  = [SCREEN_X2, SCREEN_Y2]
		self.mouseSpeed = [0, 0]
		self.renderer   = None                                   # type: Renderer
		self.running    = True
		self.screen     = None                                   # type: pygame.Surface
		self.sounds     = [None] * len(SOUND_SOURCES)
		self.volume     = 1.0

		self.loop     = pyuv.Loop.default_loop()
		self.signal_h = pyuv.Signal(self.loop)

	# HELPERS
	#########

	def Grab(self, grab: bool):
		if grab: pygame.mouse.set_pos(SCREEN_X2, SCREEN_Y2)
		pygame.mouse.set_visible(not grab)
		pygame.event.set_grab(grab)
		self.grab = grab

	def UpdateTitle(self):
		status = 'CONN' if self.connected else 'DISC'
		pygame.display.set_caption(f'[{status}] id={self.id} x={self.mouseAbs[0]} y={self.mouseAbs[1]} key={self.lastKey} fps={self.clock.get_fps():.1f}')

	# NETWORK
	#########

	def OnConnect(self, server: pyuv.TCP, error: int):
		if error:
			self.connected = False
			return
		print('OnConnect', error)
		self.connected = True
		self.Send(server, f'I{self.id}\r\n')
		server.start_read(self.OnRead)

	def OnRead(self, server: pyuv.TCP, data: bytes, error: int):
		if data is None:
			print('OnRead: Disconnected')
			self.connected = False
			self.client.close()
			self.client = None
			return

		for line in data.decode().split('\r\n'):
			if not line: continue

			# 1) game
			# ball
			if line[0] == 'B':
				items = line[1:].split(':')
				bid   = DefaultInt(items[0], -1)
				if 0 <= bid < len(self.balls):
					self.balls[bid].Parse(items)
					self.doneFrame = 0
					self.start     = time()
			# paddle
			elif line[0] == 'P':
				items = line[1:].split(':')
				pid   = DefaultInt(items[0], -1)
				if 0 <= pid < len(self.paddles) and pid != self.id:
					self.paddles[pid].Parse(items)

			# 2) connection
			elif line[0] == 'I':
				self.id = data[1] - ord('0')
				self.UpdateTitle()
			else:
				print('server:', line)

	def Signal(self, handle: pyuv.Signal, signum: int):
		self.signal_h.close()
		self.client.close()
		self.client  = None
		self.running = False

	# GAME
	######

	def Draw(self):
		self.screen.fill((96, 96, 96))

		for pid, paddle in enumerate(self.paddles):
			if not paddle.alive: continue

			# color = (0, 160, 255) if self.id == -1 or self.id != pid else (0, 255, 255)
			color = PADDLE_COLORS[pid]
			x     = paddle.position[0] * SCALE + SCREEN_X2
			y     = -paddle.position[1] * SCALE + SCREEN_Y2
			self.renderer.DrawQuad(x, y, PADDLE_X2 * SCALE, PADDLE_Y2 * SCALE, paddle.angle, color)

		for ball in self.balls:
			if not ball.alive: continue

			x = ball.position[0] * SCALE + SCREEN_X2
			y = -ball.position[1] * SCALE + SCREEN_Y2
			# pygame.draw.circle(self.screen, (0, 255, 0), (x, y), BALL_X2)
			# print(body)
			self.renderer.DrawCircle(x, y, BALL_X2 * SCALE, ball.angle, (0, 255, 0))

	def NewGame(self):
		super(PongClient, self).NewGame()
		self.PlaySound(0)

	def Physics(self):
		# 1) mouse
		self.mouseSpeed[0] += self.mouseAccel[0]
		self.mouseSpeed[1] += self.mouseAccel[1]

		self.mouseAbs[0] += self.mouseSpeed[0]
		self.mouseAbs[1] += self.mouseSpeed[1]

		# if self.mouseAbs[0] < PADDLE_Y2:
		# 	self.mouseSpeed[0] = abs(self.mouseSpeed[0]) * PADDLE_BOUNCE
		# 	self.mouseAbs[0]   = PADDLE_Y2
		# elif self.mouseAbs[0] > SCREEN_X - PADDLE_Y2:
		# 	self.mouseSpeed[0] = -abs(self.mouseSpeed[0]) * PADDLE_BOUNCE
		# 	self.mouseAbs[0]   = SCREEN_X - PADDLE_Y2

		# if self.mouseAbs[1] < PADDLE_Y2:
		# 	self.mouseSpeed[1] = abs(self.mouseSpeed[1]) * PADDLE_BOUNCE
		# 	self.mouseAbs[1]   = PADDLE_Y2
		# elif self.mouseAbs[1] > SCREEN_Y - PADDLE_Y2:
		# 	self.mouseSpeed[1] = -abs(self.mouseSpeed[1]) * PADDLE_BOUNCE
		# 	self.mouseAbs[1]   = SCREEN_Y - PADDLE_Y2

		self.mouseAccel[0] = -self.mouseSpeed[0] * 0.07
		self.mouseAccel[1] = -self.mouseSpeed[1] * 0.07

		# disconnected => move all paddles
		if not self.connected:
			pass
		# 	for paddle in self.paddles:
		# 		if paddle.angle:
		# 			paddle.x = self.mouseAbs[0]
		# 		else:
		# 			paddle.y = self.mouseAbs[1]
		# connected
		elif 0 <= self.id <= 3:
			paddle = self.paddles[self.id]
		# 	if paddle.angle:
		# 		paddle.x = self.mouseAbs[0]
		# 	else:
		# 		paddle.y = self.mouseAbs[1]

		super(PongClient, self).Physics()

	def PlaySound(self, sid: int):
		if sid >= len(self.sounds): return

		source = SOUND_SOURCES[sid]
		if not (sound := self.sounds[sid]):
			sound            = pygame.mixer.Sound(os.path.join(SOUND_PATH, source))
			self.sounds[sid] = sound

		sound.set_volume(self.volume)
		sound.play()

	def Sync(self):
		if self.mouseAbs[0] != self.mousePrev[0] or self.mouseAbs[1] != self.mousePrev[1]:
			paddle = self.paddles[self.id]
			self.Send(self.client, paddle.Format())
			self.mousePrev[0] = self.mouseAbs[0]
			self.mousePrev[1] = self.mouseAbs[1]

	# MAIN LOOP
	###########

	def Run(self):
		pygame.init()
		pygame.mixer.init()
		self.renderer = self.rendererClass()

		flags = pygame.DOUBLEBUF
		if self.renderer.name == 'opengl': flags |= pygame.OPENGL

		self.screen          = pygame.display.set_mode((SCREEN_X, SCREEN_Y), flags=flags)
		self.renderer.screen = self.screen

		self.signal_h.start(self.Signal, signal.SIGINT)

		self.Grab(True)
		self.NewGame()

		connectTime = 0

		while self.running:
			# 0) reconnect
			if not self.connected:
				if (now := time()) > connectTime + self.reconnect:
					connectTime = now
					self.client = pyuv.TCP(self.loop)
					self.client.connect((self.host, self.port), self.OnConnect)

			# 1) uv_loop
			self.loop.run(pyuv.UV_RUN_NOWAIT)

			# 2) SDL events
			events = pygame.event.get()
			for event in events:
				type_ = event.type
				if type_ == pygame.QUIT:              self.running = False
				elif type_ == pygame.KEYDOWN:         self.keys[event.key] = self.frame
				elif type_ == pygame.KEYUP:           self.keys.pop(event.key, None)
				elif type_ == pygame.MOUSEBUTTONDOWN: self.Grab(True)
				# mouse controls
				elif type_ == pygame.MOUSEMOTION:
					self.mouseAbs[0] += event.pos[0] - self.mousePos[0]
					self.mouseAbs[1] += event.pos[1] - self.mousePos[1]
					if self.grab:
						pygame.mouse.set_pos(SCREEN_X2, SCREEN_Y2)
						self.mousePos[0] = SCREEN_X2
						self.mousePos[1] = SCREEN_Y2
					else:
						self.mousePos[0] = event.pos[0]
						self.mousePos[1] = event.pos[1]

			for key, value in self.keys.items():
				# keyboard controls
				if key == pygame.K_DOWN:    self.mouseAccel[1] = PADDLE_ACCEL
				elif key == pygame.K_LEFT:  self.mouseAccel[0] = -PADDLE_ACCEL
				elif key == pygame.K_RIGHT: self.mouseAccel[0] = PADDLE_ACCEL
				elif key == pygame.K_UP:    self.mouseAccel[1] = -PADDLE_ACCEL
				# rare keys
				elif value == self.frame:
					if key == pygame.K_ESCAPE: self.running = False
					elif key == pygame.K_F1:   self.AddBall()
					elif key == pygame.K_F2:   self.ResetBalls()
					elif key == pygame.K_F3:   self.NewGame()
					elif key == pygame.K_F10:  self.client.write(b'I')
					elif key == pygame.K_TAB:  self.Grab(False)
					else:                      self.lastKey = key

			# 3) step
			self.PhysicsLoop(self.interpolate)
			self.Draw()
			self.Sync()
			self.UpdateTitle()

			pygame.display.flip()

			self.clock.tick()
			self.frame += 1


def MainClient(**kwargs):
	print(f'Client: pyuv={pyuv.__version__}')
	client = PongClient(**kwargs)
	client.Run()
	print('Goodbye.')


if __name__ == '__main__':
	MainClient()
