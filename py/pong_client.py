# coding: utf-8
# @author octopoulo <polluxyz@gmail.com>
# @version 2022-07-29

"""
Pong client
"""

import signal
from time import time

import pygame
import pyuv

from pong_common import *


class PongClient(Pong):
	def __init__(self):
		super(PongClient, self).__init__()
		print('PongClient')

		self.client = None
		self.clock = None
		self.doneFrame = 0
		self.frame = 0
		self.grab = True
		self.hit = 0
		self.keys = {}
		self.lastKey = ''
		self.mouseAbs = [SCREEN_X2, SCREEN_Y2]
		self.mouseAccel = [0, 0]
		self.mousePos = [SCREEN_X2, SCREEN_Y2]
		self.mousePrev = [SCREEN_X2, SCREEN_Y2]
		self.mouseSpeed = [0, 0]
		self.running = True
		self.screen = None
		self.start = time()

		self.loop = pyuv.Loop.default_loop()
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
		self.Send(server, b'I\r\n')
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
				bid = int(items[0])
				if bid < len(self.balls):
					self.balls[bid].Parse(items)
					self.doneFrame = 0
					self.start = time()
			# paddle
			elif line[0] == 'P':
				items = line[1:].split(':')
				pid = int(items[0])
				if pid < len(self.paddles) and pid != self.id:
					self.paddles[pid].Parse(items)

			# 2) connection
			elif line[0] == 'I':
				self.id = data[1] - ord('0')
				print('id=', self.id)
				self.UpdateTitle()
			else:
				print('server:', line)

	def Signal(self, handle: pyuv.Signal, signum: int):
		self.signal_h.close()
		self.client.close()
		self.client = None
		self.running = False

	# GAME
	######

	def Draw(self):
		self.screen.fill((96, 96, 96))

		for pid, paddle in enumerate(self.paddles):
			if not paddle.alive: continue

			color = (0, 160, 255) if self.id == -1 or self.id != pid else (0, 255, 255)
			if paddle.horiz:
				pygame.draw.rect(self.screen, color, (paddle.x - PADDLE_Y2, paddle.y - PADDLE_X2, PADDLE_Y, PADDLE_X))
			else:
				pygame.draw.rect(self.screen, color, (paddle.x - PADDLE_X2, paddle.y - PADDLE_Y2, PADDLE_X, PADDLE_Y))

		for ball in self.balls:
			if not ball.alive: continue
			pygame.draw.line(self.screen, (255, 0, 0), (ball.x - ball.vx * 16, ball.y - ball.vy * 16), (ball.x, ball.y), 2)
			pygame.draw.rect(self.screen, (255, 255, 0), (ball.x - BALL_X2, ball.y - BALL_Y2, BALL_X, BALL_Y))

		pygame.draw.circle(self.screen, (0, 255, 0), (self.ball.position[0] * 100 + SCREEN_X2, -self.ball.position[1] * 100 + SCREEN_Y2), BALL_X2)

	def Physics(self):
		# 1) mouse
		self.mouseAbs[0] += self.mouseSpeed[0]
		self.mouseAbs[1] += self.mouseSpeed[1]
		self.mouseSpeed[0] -= self.mouseSpeed[0] * 0.07
		self.mouseSpeed[1] -= self.mouseSpeed[1] * 0.07

		self.mouseAbs[0] = max(PADDLE_Y2, min(self.mouseAbs[0], SCREEN_X - PADDLE_Y2))
		self.mouseAbs[1] = max(PADDLE_Y2, min(self.mouseAbs[1], SCREEN_Y - PADDLE_Y2))

		# disconnected => move all paddles
		if not self.connected:
			for paddle in self.paddles:
				if paddle.horiz:
					paddle.x = self.mouseAbs[0]
				else:
					paddle.y = self.mouseAbs[1]
		# connected
		elif 0 <= self.id <= 3:
			paddle = self.paddles[self.id]
			if paddle.horiz:
				paddle.x = self.mouseAbs[0]
			else:
				paddle.y = self.mouseAbs[1]

		# 2) balls
		if self.MoveBalls():
			self.hit = time()

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
		self.screen = pygame.display.set_mode((SCREEN_X, SCREEN_Y), flags=pygame.DOUBLEBUF)
		self.clock = pygame.time.Clock()
		self.signal_h.start(self.Signal, signal.SIGINT)

		self.Grab(True)
		self.ResetBalls()

		self.start = time()
		connectTime = 0

		while self.running:
			# 0) reconnect
			if not self.connected:
				if (now := time()) > connectTime + 3:
					connectTime = now
					self.client = pyuv.TCP(self.loop)
					self.client.connect(('127.0.0.1', 1234), self.OnConnect)

			# 1) uv_loop
			self.loop.run(pyuv.UV_RUN_NOWAIT)

			# 2) SDL events
			events = pygame.event.get()
			for event in events:
				type_ = event.type
				if type_ == pygame.QUIT: self.running = False
				elif type_ == pygame.KEYDOWN: self.keys[event.key] = self.frame
				elif type_ == pygame.KEYUP: self.keys.pop(event.key, None)
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
				if key == pygame.K_DOWN:    self.mouseSpeed[1] += PADDLE_ACCEL
				elif key == pygame.K_LEFT:  self.mouseSpeed[0] -= PADDLE_ACCEL
				elif key == pygame.K_RIGHT: self.mouseSpeed[0] += PADDLE_ACCEL
				elif key == pygame.K_UP:    self.mouseSpeed[1] -= PADDLE_ACCEL
				# rare keys
				elif value == self.frame:
					if key == pygame.K_ESCAPE: self.running = False
					elif key == pygame.K_F1:   self.ResetBalls()
					elif key == pygame.K_F10:  self.client.write(b'I')
					elif key == pygame.K_TAB:  self.Grab(False)
					else: self.lastKey = key

			# 3) step
			elapsed = time() - self.start
			wantFrame = elapsed * PHYSICS_FPS

			# print('frame=', self.frame, 'done=', self.doneFrame, 'want=', wantFrame)
			while self.doneFrame < wantFrame:
				self.Physics()
				self.doneFrame += 1

			self.Draw()
			self.Sync()
			self.UpdateTitle()

			pygame.display.flip()

			self.clock.tick(360)
			self.frame += 1


def MainClient():
	print(f'Client: pyuv={pyuv.__version__}')
	client = PongClient()
	client.Run()
	print('Goodbye.')


if __name__ == '__main__':
	MainClient()
