# coding: utf-8
# @author octopoulo <polluxyz@gmail.com>
# @version 2022-08-04

"""
Pong client
"""

from math import copysign, pi
import os
from random import random
import signal
import struct
from time import time
from typing import List, Tuple

import pygame
import pyuv

from common import DefaultInt
from pong_common import Ball, BALL_X2, Paddle, PADDLE_FAR2, PADDLE_HIT, PADDLE_IMPULSE, PADDLE_NEAR2, PADDLE_X2, \
	PADDLE_Y2, Pong, SUN_RADIUS, TIMEOUT_DISCONNECT, TIMEOUT_PING, UdpHeader, WALL_THICKNESS, ZONE_X2, ZONE_Y2
from renderer_basic import Renderer, RendererBasic
from renderer_opengl import RendererOpenGL


RENDERERS = {
	'basic': RendererBasic,
	'opengl': RendererOpenGL,
}

ACTION_BALL_1      = 1
ACTION_BALL_2      = 2
ACTION_BALL_3      = 3
ACTION_BALL_4      = 4
ACTION_BALL_ADD    = 5
ACTION_BALL_DELETE = 6
ACTION_BALL_RESET  = 7
ACTION_DEBUG_INPUT = 8
ACTION_EXIT        = 9
ACTION_GAME_AI     = 10
ACTION_GAME_NEW1   = 11
ACTION_GAME_NEW3   = 12
ACTION_GAME_NEW5   = 13
ACTION_GAME_NEW7   = 14
ACTION_MOUSE_GRAB  = 15
ACTION_PAUSE       = 16
ACTION_PAUSE_STEP  = 17

# ps4 defaults
AXES_ZERO      = [0, 0, 0, 0, -1, -1]
AXIS_DEADZONE  = 0.1
AXIS_THRESHOLD = 0.92
AXIS_X1        = 0
AXIS_Y1        = 1
AXIS_X2        = 2
AXIS_Y2        = 3
AXIS_LTRIGGER  = 4
AXIS_RTRIGGER  = 5

BUTTON_CROSS    = 1 << 0
BUTTON_CIRCLE   = 1 << 1
BUTTON_SQUARE   = 1 << 2
BUTTON_TRIANGLE = 1 << 3
BUTTON_SELECT   = 1 << 4
BUTTON_HOME     = 1 << 5
BUTTON_START    = 1 << 6
BUTTON_L3       = 1 << 7
BUTTON_R3       = 1 << 8
BUTTON_L1       = 1 << 9
BUTTON_R1       = 1 << 10
BUTTON_UP       = 1 << 11
BUTTON_DOWN     = 1 << 12
BUTTON_LEFT     = 1 << 13
BUTTON_RIGHT    = 1 << 14
BUTTON_TOUCH    = 1 << 15

NAME_PADS = {
	'PS4 Controller': [None, None],
}

BALL_COLORS = (
	(0  , 220, 0  ),
	(0  , 0  , 255),
	(255, 0  , 0  ),
	(255, 255, 0  ),
	(0  , 255, 255),
	(255, 0  , 255),
	(255, 255, 255),
)

PADDLE_COLORS = (
	(255, 200, 0  ),
	(255, 0  , 200),
	(255, 50 , 50 ),
	(0  , 150, 255),
)

PY_PATH    = os.path.dirname(__file__)
PONG_PATH  = os.path.abspath(PY_PATH + '/..')
DATA_PATH  = os.path.join(PONG_PATH, 'data')
SOUND_PATH = os.path.join(PONG_PATH, 'sound')

SOUND_SOURCES = [
	'ball3',
	'ball2',
	'ball3',
	'ball1',
	'',
]

# others
FONT_SIZE     = 0.3
TIMEOUT_ANGLE = 0.4
TIMEOUT_MOVE  = 0.6


class PongClient(Pong):
	def __init__(self, **kwargs):
		super(PongClient, self).__init__(**kwargs)
		print('PongClient', kwargs)

		# options
		self.fpsLimit      = DefaultInt(kwargs.get('fps'), 0)
		self.interpolate   = DefaultInt(kwargs.get('interpolate'), 0)
		self.rendererClass = RENDERERS[kwargs.get('renderer')]
		self.size          = DefaultInt(kwargs.get('size'), 1280)
		self.size2         = self.size / 2

		self.actions      = {}
		self.aiControl    = 0                                      # AI plays for the player
		self.axes         = AXES_ZERO[:]                           # axes values
		self.clientTcp    = None                                   # type: pyuv.TCP
		self.clock        = pygame.time.Clock()
		self.connected    = False
		self.debug        = 0                                      # &1: inputs
		self.font         = None                                   # type: pygame.font.Font
		self.font2        = None                                   # type: pygame.font.Font
		self.fontSize     = 32
		self.fontSize2    = 48
		self.gamepad      = 0
		self.grab         = True
		self.hasMoved     = False
		self.hit          = 0
		self.keyActions   = {}
		self.keyButtons   = {}
		self.keyFlag      = 0                                      # actions pushed, from keyboard
		self.keys         = {}
		self.lastKey      = ''
		self.mouseAbs     = [self.size2, self.size2]
		self.mouseButtons = {}
		self.mousePos     = [self.size2, self.size2]
		self.nextPause    = 0
		self.padAxes      = list(range(6))                         # axis mapping
		self.padButtons   = list(range(16))                        # button mapping
		self.padFlag      = 0                                      # actions pushed, from gamepad
		self.paused       = 0
		self.pingTime     = time()
		self.pongTime     = time()
		self.randAngle    = [0.5, 0.0]                             # decide to rotate
		self.randMove     = [0.5, 0.0]                             # decide edge or center
		self.renderer     = None                                   # type: Renderer
		self.running      = True
		self.scale        = self.size2 / 6
		self.screen       = None                                   # type: pygame.Surface
		self.sounds       = [None] * len(SOUND_SOURCES)
		self.volume       = 1.0

		self.loop     = pyuv.Loop.default_loop()
		self.signal_h = pyuv.Signal(self.loop)

	# HELPERS
	#########

	def Grab(self, grab: bool):
		if grab: pygame.mouse.set_pos(self.size2, self.size2)
		pygame.mouse.set_visible(not grab)
		pygame.event.set_grab(grab)
		self.grab = grab

	def UpdateTitle(self):
		status = 'CONN' if self.connected else 'DISC'
		pygame.display.set_caption(f'BattlePong [{status}] div={self.numDiv} ai={self.aiControl} id={self.id} key={self.lastKey} fps={self.clock.get_fps():.1f}')

	# NETWORK
	#########

	def CheckReconnect(self):
		mustPing = 0
		now      = time()
		if now > self.pongTime + TIMEOUT_DISCONNECT:
			mustPing = 2
		elif now > self.pongTime + TIMEOUT_PING:
			mustPing = 1

		if mustPing and now > self.pingTime + TIMEOUT_PING:
			if mustPing == 2:
				print('CheckReconnect: disconnected')
				self.connected = False
				self.Send(self.address, struct.pack('Bb', ord('I'), self.id))
			else:
				self.Send(self.address, b'p')
			self.pingTime = now

	def Signal(self, handle: pyuv.Signal, signum: int):
		self.signal_h.close()

		if self.clientTcp:
			self.clientTcp.close()
			self.clientTcp = None

		if self.udpHandle:
			self.udpHandle.close()
			self.udpHandle = None

		self.running = False

	def UdpClientRead(self, handle: pyuv.UDP, address: Tuple[str, int], flags: int, data: bytes, error: int):
		if data is None: return

		seq   = self.udpHeader.Parse(data[:UdpHeader.structSize])
		delta = seq - self.seqRecv
		# 100 => 65000
		if delta > 32768 or -32768 < delta < 0:
			print('seq is older', seq, '<', self.seqRecv)
		else:
			self.seqRcv = seq

		data           = data[UdpHeader.structSize:]
		now            = time()
		self.connected = True
		self.pongTime  = now

		# 1) game
		# ball
		if data[0] == ord('B'):
			bid = data[1]
			while bid >= len(self.balls): self.AddBall()

			self.balls[bid].Parse(data[:Ball.structSize])
			self.doneFrame = 0
			self.start     = now

		# paddle
		elif data[0] == ord('P'):
			pid = data[1]
			if 0 <= pid < len(self.paddles): self.paddles[pid].Parse(data[:Paddle.structSize])
			data = data[Paddle.structSize:]

		# wall
		elif data[0] == ord('W'):
			wid    = data[1]
			health = data[2]
			if wid < len(self.walls):
				self.walls[wid] = health
				self.CalculateHealth(wid // self.numDiv, False)

			data = data[4:]

		# 2) connection
		elif data[0] == ord('p'): self.Send(self.address, b'q')
		elif data[0] == ord('q'): print('pong!', now)

		elif data[0] == ord('I'):
			self.id = data[1]
			data    = data[2:]
			self.UpdateTitle()
		else:
			print('TcpServer:', data)

	# GAME
	######

	def AiControls(self, id: int) -> Tuple[List[float], int]:
		paddle = self.paddles[id]
		if not paddle.alive: return AXES_ZERO, 0

		# 1) find closest ball
		horiz   = 1 if paddle.angle0 > 0 else 0
		pbody   = paddle.body
		ppos    = pbody.position
		best    = self.balls[0]
		bestDot = 1000

		if len(self.balls) > 0:
			best = None

			for ball in self.balls:
				bbody   = ball.body
				bpos    = bbody.position
				bvel    = bbody.linearVelocity
				ballDot = 1000

				# ball is coming towards us?
				dx0  = bpos[0] - paddle.position0[0]
				dy0  = bpos[1] - paddle.position0[1]
				# dots = []
				for i in range(5):
					dx1     = dx0 if horiz == 0 else dx0 - (i - 2) * ZONE_X2
					dy1     = dy0 if horiz == 1 else dy0 - (i - 2) * ZONE_Y2
					dist2   = dx1 * dx1 + dy1 * dy1 + 0.1
					dot     = (dx1 * bvel[0] + dy1 * bvel[1]) / dist2
					ballDot = min(ballDot, dot)
					# dots.append(int(dot * 100) / 100)

				if ballDot < 0 and ballDot < bestDot:
					best    = ball
					bestDot = ballDot
				# print(f'bid={ball.id} bdot={ballDot:.2f} best={bestDot:.2f} {best.id if best else "X"}', dots)

		# 2) move
		bpos    = best.body.position if best else paddle.position0
		dx      = bpos[0] - ppos[0]
		dy      = bpos[1] - ppos[1]
		dist2   = dx * dx + dy * dy
		buttons = 0

		randMove = self.RandomDecision(self.randMove, TIMEOUT_MOVE) - 0.5

		if paddle.angle0 > 0:
			# ball behind => give it some space
			if dist2 < PADDLE_FAR2:
				if paddle.position0[1] < 0:
					if dy < 0: dx = -dx
				elif dy > 0: dx = -dx

			dx += randMove * PADDLE_Y2

			if dx > 0:   buttons |= BUTTON_RIGHT
			elif dx < 0: buttons |= BUTTON_LEFT
		else:
			# ball behind => give it some space
			if dist2 < PADDLE_FAR2:
				if paddle.position0[0] < 0:
					if dx < 0: dy = -dy
				elif dx > 0: dy = -dy

			dy += randMove * PADDLE_Y2

			if dy > 0:   buttons |= BUTTON_UP
			elif dy < 0: buttons |= BUTTON_DOWN

		# 3) rotate hit?
		if dist2 < PADDLE_NEAR2:
			randAngle = self.RandomDecision(self.randAngle, TIMEOUT_ANGLE)
			buttons |= (BUTTON_L1 if randAngle > 0.5 else BUTTON_R1)

		return AXES_ZERO, buttons

	def Controls(self):
		self.GamePadUpdate()

		# 1) mouse
		self.mouseAbs[0] = min(max(self.mouseAbs[0], PADDLE_Y2 * self.scale), self.size - PADDLE_Y2 * self.scale)
		self.mouseAbs[1] = min(max(self.mouseAbs[1], PADDLE_Y2 * self.scale), self.size - PADDLE_Y2 * self.scale)

		# disconnected => move all paddles
		if self.id >= 0:
			ids = [self.id]
			if self.id > 3: return
		else:
			ids = [0, 1, 2, 3]

		for id in ids:
			paddle = self.paddles[id]
			if not paddle.alive: continue

			# 2) gamepad + keyboard + AI inputs
			if id != max(0, self.id):
				axes, pad = self.AiControls(id)
			else:
				axes = self.axes
				pad  = self.padFlag | self.keyFlag
				if self.aiControl: pad |= self.AiControls(id)[1]

			axisX = axes[AXIS_X1] + axes[AXIS_X2]
			axisY = axes[AXIS_Y1] + axes[AXIS_Y2]

			if pad & BUTTON_DOWN:  axisY += 1
			if pad & BUTTON_LEFT:  axisX -= 1
			if pad & BUTTON_RIGHT: axisX += 1
			if pad & BUTTON_UP:    axisY -= 1

			axisX = min(max(axisX, -1), 1)
			axisY = min(max(axisY, -1), 1)

			# 3) apply inputs
			horiz  = paddle.angle0 > 0
			body   = paddle.body
			center = body.worldCenter

			# hitting the ball
			if (pad & (BUTTON_SQUARE | BUTTON_L1)) or axes[AXIS_LTRIGGER] > -1:
				self.hasMoved = True
				value = (1 if (pad & (BUTTON_SQUARE | BUTTON_L1)) else (axes[AXIS_LTRIGGER] + 1) / 2) * PADDLE_HIT
				if horiz:
					if paddle.position0[1] < 0:
						if body.angle < pi / 2 + pi / 16: body.ApplyAngularImpulse(value, True)
					elif body.angle > pi / 2 - pi / 16: body.ApplyAngularImpulse(-value, True)
				elif body.angle < pi / 16: body.ApplyAngularImpulse(value, True)

			if (pad & (BUTTON_CIRCLE | BUTTON_R1)) or axes[AXIS_RTRIGGER] > -1:
				self.hasMoved = True
				value = (1 if (pad & (BUTTON_CIRCLE | BUTTON_R1)) else (axes[AXIS_RTRIGGER] + 1) / 2) * PADDLE_HIT
				if horiz:
					if paddle.position0[1] < 0:
						if body.angle > pi / 2 - pi / 16: body.ApplyAngularImpulse(-value, True)
					elif body.angle < pi / 2 + pi / 16: body.ApplyAngularImpulse(value, True)
				elif body.angle > -pi / 16: body.ApplyAngularImpulse(-value, True)

			# movement
			if axisX and horiz:
				self.hasMoved = True
				body.ApplyLinearImpulse((PADDLE_IMPULSE * axisX, 0), center, True)
			if axisY and not horiz:
				self.hasMoved = True
				body.ApplyLinearImpulse((0, -PADDLE_IMPULSE * axisY), center, True)

			paddle.buttons = pad

	def Draw(self):
		self.screen.fill((40, 40, 40))

		scale = self.scale
		size2 = self.size2

		# walls
		vertices  = self.wall.fixtures[0].shape.vertices
		numVertex = len(vertices)

		for i in range(numVertex - (numVertex & 1)):
			x, y   = vertices[i]
			x2, y2 = vertices[(i + 1) % numVertex]
			# if not self.frame: print(i, numVertex, (x, y), (x2, y2))
			health = self.walls[i] / 255
			thick  = max(int(WALL_THICKNESS * scale), 2)
			thick2 = max(int(thick / 4 + 0.5), 2)

			self.renderer.DrawLine(
				x * scale + size2 + (-thick2 if x == ZONE_X2 else 0),
				-y * scale + size2 + (-thick2 if -y == ZONE_X2 else 0),
				x2 * scale + size2 + (-thick2 if x2 == ZONE_X2 else 0),
				-y2 * scale + size2 + (-thick2 if -y2 == ZONE_X2 else 0),
				(240 - 40 * health, 50 + 150 * health, 0 + 240 * health) if health > 0 else (40, 40, 40),
				thick
			)

		# sun
		if self.sun:
			x = self.sun.position[0] * scale + size2
			y = self.sun.position[1] * scale + size2
			self.renderer.DrawCircle(x, y, SUN_RADIUS * scale, self.sun.angle, (220, 110, 40), False)

		# show pad/mouse inputs
		if self.debug & 1:
			gap   = self.fontSize * 1.25
			size4 = size2 / 2

			for i, axis in enumerate(self.axes):
				self.DrawText(size4, size4 + i * gap, f'{i}: {axis:.3f}', (128, 128, 128))
			for i in range(16):
				self.DrawText(size4 * 3, size4 + i * gap, f'{i}: {self.padFlag & (1 << i)}', (128, 128, 128))
			self.DrawText(size4, size4 + 7 * gap, f'{self.mouseAbs[0]:.0f} {self.mouseAbs[1]:.0f}', (128, 128, 128))

			for pid, paddle in enumerate(self.paddles):
				self.DrawText(size4, size4 + (9 + pid) * gap, f'{paddle.buttons}', (128, 128, 128))

		# paddles
		for pid, paddle in enumerate(self.paddles):
			self.DrawText(paddle.position0[0] * 1.08 * scale + size2, -paddle.position0[1] * 1.08 * scale + size2, f'{paddle.health}')

			color = PADDLE_COLORS[pid] if self.id == -1 or self.id != pid else (0, 255, 255)
			if not paddle.alive: color = (80 + color[0] * 0.1, 80 + color[1] * 0.1, 80 + color[2] * 0.1)

			x = paddle.position[0] * scale + size2
			y = -paddle.position[1] * scale + size2
			self.renderer.DrawQuad(x, y, PADDLE_X2 * scale, PADDLE_Y2 * scale, paddle.angle, color)

		# balls
		numColor = len(BALL_COLORS)
		for bid, ball in enumerate(self.balls):
			if not ball.alive: continue

			color = BALL_COLORS[bid % numColor]
			x     = ball.position[0] * scale + size2
			y     = -ball.position[1] * scale + size2
			self.renderer.DrawCircle(x, y, BALL_X2 * scale, ball.angle, color, True)

	def DrawText(self, x: int, y: int, text: str, color: Tuple[int, int, int] = (200, 200, 200)):
		textObj         = self.font.render(text, True, color)
		textRect        = textObj.get_rect()
		textRect.center = (x, y)
		self.screen.blit(textObj, textRect)

	def GameKeyDown(self, key: int):
		action = self.keyActions.get(key)

		if action == ACTION_EXIT:          self.running = False
		elif action == ACTION_BALL_1:      self.SetBalls(1)
		elif action == ACTION_BALL_2:      self.SetBalls(2)
		elif action == ACTION_BALL_3:      self.SetBalls(3)
		elif action == ACTION_BALL_4:      self.SetBalls(4)
		elif action == ACTION_BALL_ADD:    self.AddBall()
		elif action == ACTION_BALL_DELETE: self.DeleteBall()
		elif action == ACTION_BALL_RESET:  self.ResetBalls()
		elif action == ACTION_DEBUG_INPUT: self.debug ^= 1
		elif action == ACTION_GAME_AI:     self.aiControl ^= 1
		elif action == ACTION_GAME_NEW1:   self.NewGame(1)
		elif action == ACTION_GAME_NEW3:   self.NewGame(3)
		elif action == ACTION_GAME_NEW5:   self.NewGame(5)
		elif action == ACTION_GAME_NEW7:   self.NewGame(7)
		elif action == ACTION_MOUSE_GRAB:  self.Grab(False)
		elif action == ACTION_PAUSE:       self.Pause(2)
		elif action == ACTION_PAUSE_STEP:  self.Pause(2, 1)
		else:                              self.lastKey = key

		self.keys[key] = self.frame
		self.keyFlag |= self.keyButtons.get(key, 0)

	def GameKeyUp(self, key: int):
		self.keys.pop(key, None)
		self.keyFlag &= ~self.keyButtons.get(key, 0)

	def GamePadInit(self):
		if not pygame.joystick.get_count():
			self.gamepad = None
			return

		self.gamepad = pygame.joystick.Joystick(0)
		self.gamepad.init()

		self.padAxes = list(range(6))
		self.padPads = list(range(16))

		if pad := NAME_PADS.get(self.gamepad.get_name()):
			if pad[0]: self.padAxes = pad[0]
			if pad[1]: self.padPads = pad[1]

		print(self.gamepad.get_name(), self.gamepad.get_guid(), self.padAxes, self.padPads)

	def GamePadUpdate(self):
		if not self.gamepad: return

		for i in range(self.gamepad.get_numbuttons()):
			flag = 1 << self.padPads[i]
			if self.gamepad.get_button(i):
				self.padFlag |= flag
			else:
				self.padFlag &= ~flag

		for i in range(self.gamepad.get_numaxes()):
			id       = self.padAxes[i]
			value    = self.gamepad.get_axis(i)
			valueAbs = abs(value)

			if (id == AXIS_LTRIGGER or id == AXIS_RTRIGGER) or valueAbs > AXIS_DEADZONE:
				self.axes[id] = copysign(1, value) if valueAbs > AXIS_THRESHOLD else value
			else:
				self.axes[id] = 0

	def MouseDown(self, button: int):
		self.keyFlag |= self.mouseButtons.get(button, 0)
		if button == 1: self.Grab(True)

	def MouseUp(self, button: int):
		self.keyFlag &= ~self.mouseButtons.get(button, 0)

	def NewGame(self, numDiv: int = 0):
		super(PongClient, self).NewGame(numDiv)
		self.PlaySound(0)

	def OpenMapping(self):
		self.keyActions = {
			pygame.K_1:            ACTION_BALL_1,
			pygame.K_2:            ACTION_BALL_2,
			pygame.K_3:            ACTION_BALL_3,
			pygame.K_4:            ACTION_BALL_4,
			pygame.K_BACKSPACE:    ACTION_BALL_RESET,
			pygame.K_ESCAPE:       ACTION_EXIT,
			pygame.K_F1:           ACTION_GAME_NEW7,
			pygame.K_F2:           ACTION_GAME_NEW5,
			pygame.K_F3:           ACTION_GAME_NEW3,
			pygame.K_F4:           ACTION_GAME_NEW1,
			pygame.K_KP_MINUS:     ACTION_BALL_DELETE,
			pygame.K_KP_PLUS:      ACTION_BALL_ADD,
			pygame.K_LEFTBRACKET:  ACTION_BALL_DELETE,
			pygame.K_o:            ACTION_PAUSE_STEP,
			pygame.K_p:            ACTION_PAUSE,
			pygame.K_RETURN:       ACTION_GAME_AI,
			pygame.K_RIGHTBRACKET: ACTION_BALL_ADD,
			pygame.K_SPACE:        ACTION_DEBUG_INPUT,
			pygame.K_TAB:          ACTION_MOUSE_GRAB,
		}
		self.keyButtons = {
			pygame.K_a:     BUTTON_LEFT,
			pygame.K_c:     BUTTON_SQUARE,
			pygame.K_d:     BUTTON_RIGHT,
			pygame.K_DOWN:  BUTTON_DOWN,
			pygame.K_e:     BUTTON_CIRCLE,
			pygame.K_LEFT:  BUTTON_LEFT,
			pygame.K_q:     BUTTON_SQUARE,
			pygame.K_RIGHT: BUTTON_RIGHT,
			pygame.K_s:     BUTTON_DOWN,
			pygame.K_UP:    BUTTON_UP,
			pygame.K_w:     BUTTON_UP,
			pygame.K_z:     BUTTON_CIRCLE,
		}
		self.mouseButtons = {
			1: BUTTON_SQUARE,
			3: BUTTON_CIRCLE,
		}

	def Pause(self, pause: int, nextPause: int = 0):
		if pause == 2:
			self.paused ^= 1
		else:
			self.paused = pause

		if self.paused == 0:
			self.doneFrame = 0
			self.start     = time()

		self.nextPause = nextPause

	def Physics(self):
		self.Controls()
		super(PongClient, self).Physics()

	def PlaySound(self, sid: int):
		if sid >= len(self.sounds): return
		if not (source := SOUND_SOURCES[sid]): return

		if not (sound := self.sounds[sid]):
			baseName = os.path.join(SOUND_PATH, source)
			for ext in ('.ogg', '.mp3', '.wav'):
				filename = baseName + ext
				if os.path.exists(filename):
					try:
						sound = pygame.mixer.Sound(filename)
						self.sounds[sid] = sound
						break
					except:
						print('Cannot open sound', filename)

		if sound:
			sound.set_volume(self.volume)
			sound.play()
		else:
			SOUND_SOURCES[sid] = None

	def PlaySounds(self):
		for i in range(5):
			if self.hitFlag & (1 << i): self.PlaySound(i)

	def RandomDecision(self, randTime: List[float], timeout: float) -> float:
		now = time()
		if now > randTime[1] + timeout:
			randTime[0] = random()
			randTime[1] = now

		return randTime[0]

	def Sync(self):
		if self.id < 0 or self.id > 3: return

		if self.hasMoved or (self.dirtyPaddle & (1 << self.id)):
			paddle = self.paddles[self.id]
			self.Send(self.address, paddle.Format())

		if self.dirtyBall:
			for ball in self.balls:
				if ball.parentId == self.id and (ball.flag & (1 << self.id)):
					self.Send(self.address, ball.Format())

		self.hasMoved = False

	# MAIN LOOP
	###########

	def Run(self):
		pygame.init()
		pygame.mixer.init()

		self.fontSize  = (int(FONT_SIZE * self.scale) // 8) * 8
		self.fontSize2 = (int(FONT_SIZE * self.scale * 1.5) // 8) * 8
		self.font      = pygame.font.Font(os.path.join(DATA_PATH, 'kenpixel.ttf'), self.fontSize)
		self.font2     = pygame.font.Font(os.path.join(DATA_PATH, 'kenpixel.ttf'), self.fontSize2)
		self.renderer  = self.rendererClass()

		flags = pygame.DOUBLEBUF
		if self.renderer.name == 'opengl': flags |= pygame.OPENGL

		self.screen          = pygame.display.set_mode((self.size, self.size), flags=flags)
		self.renderer.screen = self.screen

		self.udpHandle = pyuv.UDP(self.loop)
		self.udpHandle.bind(('127.0.0.1', 0))
		self.udpHandle.start_recv(self.UdpClientRead)
		self.Send(self.address, struct.pack('Bb', ord('I'), self.id))

		self.signal_h.start(self.Signal, signal.SIGINT)

		self.GamePadInit()
		self.OpenMapping()

		self.Grab(True)
		self.NewGame()
		# self.AddBall(2)

		while self.running:
			# 0) reconnect
			if self.reconnect: self.CheckReconnect()

			# 1) uv_loop
			self.loop.run(pyuv.UV_RUN_NOWAIT)

			# 2) SDL events
			events = pygame.event.get()
			for event in events:
				type_ = event.type
				if type_ == pygame.QUIT:               self.running = False
				elif type_ == pygame.JOYDEVICEADDED:   self.GamePadInit()
				elif type_ == pygame.JOYDEVICEREMOVED: self.GamePadInit()
				elif type_ == pygame.KEYDOWN:          self.GameKeyDown(event.key)
				elif type_ == pygame.KEYUP:            self.GameKeyUp(event.key)
				elif type_ == pygame.MOUSEBUTTONDOWN:  self.MouseDown(event.button)
				elif type_ == pygame.MOUSEBUTTONUP:    self.MouseUp(event.button)
				# mouse controls
				elif type_ == pygame.MOUSEMOTION:
					self.mouseAbs[0] += event.pos[0] - self.mousePos[0]
					self.mouseAbs[1] += event.pos[1] - self.mousePos[1]
					if self.grab:
						pygame.mouse.set_pos(self.size2, self.size2)
						self.mousePos[0] = self.size2
						self.mousePos[1] = self.size2
					else:
						self.mousePos[0] = event.pos[0]
						self.mousePos[1] = event.pos[1]

			# 3) step
			if self.paused == 0:
				self.PhysicsLoop(self.interpolate)
				self.PlaySounds()

				if self.nextPause and self.doneFrame > 0:
					self.paused    = 1
					self.nextPause = 0

			self.Draw()
			self.Sync()
			self.UpdateTitle()

			pygame.display.flip()

			self.clock.tick(self.fpsLimit)
			self.frame += 1


def MainClient(**kwargs):
	print(f'Client: pyuv={pyuv.__version__}')
	client = PongClient(**kwargs)
	client.Run()
	print('Goodbye.')


if __name__ == '__main__':
	MainClient()
