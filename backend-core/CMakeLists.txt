cmake_minimum_required(VERSION 3.16)
project(storyteller LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(STORY_COVERAGE "Instrument the library for coverage reports" OFF)
option(STORY_TESTS "Build the test suite" ON)

include(FetchContent)
FetchContent_Declare(json
  URL https://github.com/nlohmann/json/releases/download/v3.11.3/json.tar.xz
  URL_HASH SHA256=d6c65aca6b1ed68e7a182f4757257b107ae403032760ed6ef121c9d55e81757d)
set(HTTPLIB_USE_OPENSSL_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_USE_ZLIB_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_USE_BROTLI_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
FetchContent_Declare(httplib
  URL https://github.com/yhirose/cpp-httplib/archive/refs/tags/v0.15.3.tar.gz)
FetchContent_MakeAvailable(json httplib)

find_package(CURL REQUIRED)

add_library(story
  src/model.cpp
  src/format.cpp
  src/config.cpp
  src/facts.cpp
  src/caveats.cpp
  src/planner.cpp
  src/realiser.cpp
  src/verifier.cpp
  src/narrative.cpp
  src/payload.cpp
  src/mutation.cpp)
target_include_directories(story PUBLIC include)
target_link_libraries(story PUBLIC nlohmann_json::nlohmann_json)
target_compile_options(story PRIVATE -Wall -Wextra -Wpedantic)
if(STORY_COVERAGE)
  target_compile_options(story PUBLIC --coverage -O0 -g)
  target_link_options(story PUBLIC --coverage)
endif()

add_library(story_net src/postgrest.cpp)
target_link_libraries(story_net PUBLIC story CURL::libcurl)

add_executable(storyteller src/main.cpp)
target_link_libraries(storyteller PRIVATE story story_net httplib::httplib)

if(STORY_TESTS)
  FetchContent_Declare(Catch2
    URL https://github.com/catchorg/Catch2/archive/refs/tags/v3.5.2.tar.gz)
  FetchContent_MakeAvailable(Catch2)
  add_executable(story_tests
    tests/test_format.cpp
    tests/test_facts.cpp
    tests/test_caveats.cpp
    tests/test_verifier.cpp
    tests/test_narrative.cpp)
  target_link_libraries(story_tests PRIVATE story Catch2::Catch2WithMain)
  target_compile_definitions(story_tests PRIVATE
    STORY_CONFIG_DIR="${CMAKE_CURRENT_SOURCE_DIR}/config"
    STORY_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
  include(CTest)
  list(APPEND CMAKE_MODULE_PATH ${catch2_SOURCE_DIR}/extras)
  include(Catch)
  catch_discover_tests(story_tests)
endif()
