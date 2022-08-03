# coding: utf-8
# @author octopoulo <polluxyz@gmail.com>
# @version 2022-08-01

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
from pong_common import BALL_X2, PADDLE_FAR2, PADDLE_HIT, PADDLE_IMPULSE, PADDLE_NEAR2, PADDLE_X2, PADDLE_Y2, Pong, \
	STRUCT_BALL, STRUCT_PADDLE, SUN_RADIUS, WALL_THICKNESS, ZONE_X2
from renderer_basic import Renderer, RendererBasic
from renderer_opengl import RendererOpenGL


RENDERERS = {
	'basic': RendererBasic,
	'opengl': RendererOpenGL,
}

ACTION_BALL_ADD    = 1
ACTION_BALL_DELETE = 2
ACTION_BALL_RESET  = 3
ACTION_DEBUG_INPUT = 4
ACTION_GAME_AI     = 5
ACTION_GAME_EXIT   = 6
ACTION_GAME_NEW    = 7
ACTION_GAME_START  = 8
ACTION_GAME_STOP   = 9
ACTION_MOUSE_GRAB  = 10

# ps4 defaults
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
		self.axes         = [0] * 6                                # axes values
		self.client       = None                                   # type: pyuv.TCP
		self.clock        = pygame.time.Clock()
		self.debug        = 0                                      # &1: inputs
		self.font         = None                                   # type: pygame.font.Font
		self.fontSize     = 32
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
		self.padAxes      = list(range(6))                         # axis mapping
		self.padButtons   = list(range(16))                        # button mapping
		self.padFlag      = 0                                      # actions pushed, from gamepad
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
		pygame.display.set_caption(f'[{status}] id={self.id} x={self.mouseAbs[0]} y={self.mouseAbs[1]} key={self.lastKey} fps={self.clock.get_fps():.1f}')

	# NETWORK
	#########

	def OnConnect(self, server: pyuv.TCP, error: int):
		if error:
			self.connected = False
			return
		print('OnConnect', error)
		self.connected = True
		self.Send(server, struct.pack('xBb', ord('I'), self.id))
		server.start_read(self.OnRead)

	def OnRead(self, server: pyuv.TCP, data: bytes, error: int):
		if data is None:
			print('OnRead: Disconnected')
			self.connected = False
			self.client.close()
			self.client = None
			return

		while len(data):
			if data[0] == 0:
				# 1) game
				# ball
				if data[1] == ord('B'):
					bid = data[2]
					while bid >= len(self.balls): self.AddBall()

					self.balls[bid].Parse(data[:STRUCT_BALL])
					self.doneFrame = 0
					self.start     = time()
					data           = data[STRUCT_BALL:]

				# paddle
				elif data[1] == ord('P'):
					pid = data[2]
					if 0 <= pid < len(self.paddles): self.paddles[pid].Parse(data[:STRUCT_PADDLE])
					data = data[STRUCT_PADDLE:]

				# 2) connection
				elif data[1] == ord('I'):
					self.id = data[2]
					data    = data[3:]
					self.UpdateTitle()
				else:
					print('server:', data)
					break
			else:
				print('server:', data)
				break

	def Signal(self, handle: pyuv.Signal, signum: int):
		self.signal_h.close()
		self.client.close()
		self.client  = None
		self.running = False

	# GAME
	######

	def AiControls(self, id: int) -> Tuple[List[float], int]:
		paddle  = self.paddles[id]
		pbody   = paddle.body
		ppos    = pbody.position
		ball    = self.balls[0]
		bbody   = ball.body
		bpos    = bbody.position
		dx      = bpos[0] - ppos[0]
		dy      = bpos[1] - ppos[1]
		dist2   = dx * dx + dy * dy
		buttons = 0

		# 1) move
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

		# 2) rotate hit?
		if dist2 < PADDLE_NEAR2:
			randAngle = self.RandomDecision(self.randAngle, TIMEOUT_ANGLE)
			buttons |= (BUTTON_L1 if randAngle > 0.5 else BUTTON_R1)

		return [0] * 6, buttons

	def Controls(self):
		self.GamePadUpdate()

		# 1) mouse
		self.mouseAbs[0] = min(max(self.mouseAbs[0], PADDLE_Y2 * self.scale), self.size - PADDLE_Y2 * self.scale)
		self.mouseAbs[1] = min(max(self.mouseAbs[1], PADDLE_Y2 * self.scale), self.size - PADDLE_Y2 * self.scale)

		# disconnected => move all paddles
		if self.id >= 0:
			ids = [self.id]
		else:
			ids = [0, 1, 2, 3]

		for id in ids:
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
			paddle = self.paddles[id]
			horiz  = paddle.angle0 > 0
			body   = paddle.body
			center = body.worldCenter

			# hitting the ball
			if (pad & (BUTTON_SQUARE | BUTTON_L1)) or axes[AXIS_LTRIGGER] > -1:
				self.hasMoved = True
				value = (1 if (pad & (BUTTON_SQUARE | BUTTON_L1)) else (axes[AXIS_LTRIGGER] + 1) / 2) * PADDLE_HIT
				if horiz:
					if paddle.position0[1] < 0:
						if body.angle > pi / 2 - pi / 16: body.ApplyAngularImpulse(-value, True)
					elif body.angle < pi / 2 + pi / 16: body.ApplyAngularImpulse(value, True)
				elif body.angle > -pi / 16: body.ApplyAngularImpulse(-value, True)

			if (pad & (BUTTON_CIRCLE | BUTTON_R1)) or axes[AXIS_RTRIGGER] > -1:
				self.hasMoved = True
				value = (1 if (pad & (BUTTON_CIRCLE | BUTTON_R1)) else (axes[AXIS_RTRIGGER] + 1) / 2) * PADDLE_HIT
				if horiz:
					if paddle.position0[1] < 0:
						if body.angle < pi / 2 + pi / 16: body.ApplyAngularImpulse(value, True)
					elif body.angle > pi / 2 - pi / 16: body.ApplyAngularImpulse(-value, True)
				elif body.angle < pi / 16: body.ApplyAngularImpulse(value, True)

			# movement
			if axisX and horiz:
				self.hasMoved = True
				body.ApplyLinearImpulse((PADDLE_IMPULSE * axisX, 0), center, True)
			if axisY and not horiz:
				self.hasMoved = True
				body.ApplyLinearImpulse((0, -PADDLE_IMPULSE * axisY), center, True)

			paddle.buttons = pad

	def Draw(self):
		self.screen.fill((80, 80, 80))

		scale = self.scale
		size2 = self.size2

		# walls
		vertices  = self.wall.fixtures[0].shape.vertices
		numVertex = len(vertices)

		for i in range(numVertex - (numVertex & 1)):
			x, y   = vertices[i]
			x2, y2 = vertices[(i + 1) % numVertex]
			# if not self.frame: print(i, numVertex, (x, y), (x2, y2))
			health = self.walls[i]
			thick  = max(int(WALL_THICKNESS * scale), 2)
			thick2 = max(int(thick / 4 + 0.5), 2)

			self.renderer.DrawLine(
				x * scale + size2 + (-thick2 if x == ZONE_X2 else 0),
				-y * scale + size2 + (-thick2 if -y == ZONE_X2 else 0),
				x2 * scale + size2 + (-thick2 if x2 == ZONE_X2 else 0),
				-y2 * scale + size2 + (-thick2 if -y2 == ZONE_X2 else 0),
				(240 - 40 * health, 80 + 120 * health, 0 + 240 * health) if health > 0 else (80, 80, 80),
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
			if not paddle.alive: continue

			self.DrawText(paddle.position0[0] * 1.08 * scale + size2, -paddle.position0[1] * 1.08 * scale + size2, f'{paddle.score}')

			# color = (0, 160, 255) if self.id == -1 or self.id != pid else (0, 255, 255)
			color = PADDLE_COLORS[pid] if self.id == -1 or self.id != pid else (0, 255, 255)
			x     = paddle.position[0] * scale + size2
			y     = -paddle.position[1] * scale + size2
			self.renderer.DrawQuad(x, y, PADDLE_X2 * scale, PADDLE_Y2 * scale, paddle.angle, color)

		# balls
		for ball in self.balls:
			if not ball.alive: continue

			x = ball.position[0] * scale + size2
			y = -ball.position[1] * scale + size2
			self.renderer.DrawCircle(x, y, BALL_X2 * scale, ball.angle, (0, 255, 0), True)

	def DrawText(self, x: int, y: int, text: str, color: Tuple[int, int, int] = (200, 200, 200)):
		textObj         = self.font.render(text, True, color)
		textRect        = textObj.get_rect()
		textRect.center = (x, y)
		self.screen.blit(textObj, textRect)

	def GameKeyDown(self, key: int):
		action = self.keyActions.get(key)

		if action == ACTION_GAME_EXIT:     self.running = False
		elif action == ACTION_BALL_ADD:    self.AddBall()
		elif action == ACTION_BALL_DELETE: self.DeleteBall()
		elif action == ACTION_BALL_RESET:  self.ResetBalls()
		elif action == ACTION_DEBUG_INPUT: self.debug ^= 1
		elif action == ACTION_GAME_AI:     self.aiControl ^= 1
		elif action == ACTION_GAME_NEW:    self.NewGame()
		elif action == ACTION_GAME_START:  self.StartGame()
		elif action == ACTION_GAME_STOP:   self.StopGame()
		elif action == ACTION_MOUSE_GRAB:  self.Grab(False)
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

	def NewGame(self):
		super(PongClient, self).NewGame()
		self.PlaySound(0)

	def OpenMapping(self):
		self.keyActions = {
			pygame.K_ESCAPE:   ACTION_GAME_EXIT,
			pygame.K_F1:       ACTION_DEBUG_INPUT,
			pygame.K_F2:       ACTION_GAME_AI,
			pygame.K_F3:       ACTION_BALL_RESET,
			pygame.K_F4:       ACTION_GAME_NEW,
			# pygame.K_F5:       ACTION_GAME_STOP,
			pygame.K_KP_MINUS: ACTION_BALL_DELETE,
			pygame.K_KP_PLUS:  ACTION_BALL_ADD,
			pygame.K_MINUS:    ACTION_BALL_DELETE,
			pygame.K_PLUS:     ACTION_BALL_ADD,
			pygame.K_TAB:      ACTION_MOUSE_GRAB,
		}
		self.keyButtons = {
			pygame.K_a:     BUTTON_LEFT,
			pygame.K_d:     BUTTON_RIGHT,
			pygame.K_DOWN:  BUTTON_DOWN,
			pygame.K_e:     BUTTON_CIRCLE,
			pygame.K_LEFT:  BUTTON_LEFT,
			pygame.K_q:     BUTTON_SQUARE,
			pygame.K_RIGHT: BUTTON_RIGHT,
			pygame.K_s:     BUTTON_DOWN,
			pygame.K_UP:    BUTTON_UP,
			pygame.K_w:     BUTTON_UP,
		}
		self.mouseButtons = {
			1: BUTTON_SQUARE,
			3: BUTTON_CIRCLE,
		}

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

	def StartGame(self):
		self.id = -1 if self.id >= 0 else 0

	def StopGame(self):
		pass

	def Sync(self):
		if self.id < 0: return

		if self.hasMoved or (self.paddleDirty & (1 << self.id)):
			paddle = self.paddles[self.id]
			self.Send(self.client, paddle.Format())

		if self.ballDirty:
			for ball in self.balls:
				if ball.parentId == self.id:
					self.Send(self.client, ball.Format())

		self.hasMoved = False

	# MAIN LOOP
	###########

	def Run(self):
		pygame.init()
		pygame.mixer.init()

		self.fontSize = (int(FONT_SIZE * self.scale) // 8) * 8
		self.font     = pygame.font.Font(os.path.join(DATA_PATH, 'kenpixel.ttf'), self.fontSize)
		self.renderer = self.rendererClass()

		flags = pygame.DOUBLEBUF
		if self.renderer.name == 'opengl': flags |= pygame.OPENGL

		self.screen          = pygame.display.set_mode((self.size, self.size), flags=flags)
		self.renderer.screen = self.screen

		self.signal_h.start(self.Signal, signal.SIGINT)

		self.GamePadInit()
		self.OpenMapping()

		self.Grab(True)
		self.NewGame()
		# self.AddBall(2)

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
			self.PhysicsLoop(self.interpolate)
			self.PlaySounds()
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
