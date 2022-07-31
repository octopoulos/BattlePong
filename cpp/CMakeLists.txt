# CMakeLists.txt
cmake_minimum_required(VERSION 3.10)

project(pong)

set(Boost_NO_WARN_NEW_VERSIONS 1)
set(CMAKE_CXX_STANDARD 20)

if (MSVC)
	set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /Zc:__cplusplus")
else()
	set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -msse4.2")
endif()

find_package(doctest CONFIG REQUIRED)
find_package(fmt CONFIG REQUIRED)
find_package(GLEW REQUIRED)
find_package(libuv CONFIG REQUIRED)
find_package(OpenGL REQUIRED)
find_package(SDL2 CONFIG REQUIRED)
find_package(sdl2-image CONFIG REQUIRED)
find_package(SDL2_mixer CONFIG REQUIRED)
find_package(sdl2-ttf CONFIG REQUIRED)

# Add source to this project's executable.
add_executable(pong
	main.cpp
	pong_client.cpp
	pong_common.h
	pong_server.cpp
	stdafx.h
	version.cpp
	)

target_precompile_headers(pong
	PUBLIC
		stdafx.h
	)

target_link_libraries(pong
	PRIVATE
		doctest::doctest
		fmt::fmt-header-only
		GLEW::GLEW
		${OPENGL_gl_LIBRARY}
		SDL2::SDL2 SDL2::SDL2main SDL2_mixer::SDL2_mixer
		$<IF:$<TARGET_EXISTS:uv_a>,uv_a,uv>
	)
