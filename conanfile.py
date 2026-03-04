#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Conan recipe package for uavia-autopilot-generic-interface
"""
import os
import sys
from conans import ConanFile, CMake, tools
from conf.dji_autopilot import DJIAutopilot
from conf.dji_light_autopilot import DJILightAutopilot
from conf.parrot_autopilot import ParrotAutopilot
from conf.ardupilot_autopilot import ArdupilotAutopilot
from conf.ardurover_autopilot import ArduRoverAutopilot
from conf.autopilot import Autopilot
from conf.utils import filter_dependencies

class UaviaAutopilotGenericInterface(ConanFile):
    """
    ConanFile class for the UaviaAutopilotGenericInterface project.
    It is used as a build system for this project.
    Take a look to the conf/<autopilot> to see autopilots options and configs.
    """

    name = "uavia-autopilot-generic-interface"
    license = "proprietary"
    author = "UAVIA Embedded Team embedded@uavia.eu"
    url = "https://github.com/uavia/uavia-autopilot-generic-interface"
    description = "UAVIA Generic Interface which allows conversion from autopilots particular messages to the generic messages"
    settings = "os", "compiler", "build_type", "arch"
    revision_mode = "scm"
    
    options = { 
        "exiv2_version": "ANY",
        "libcurl_version": "ANY",
        "protobuf_version": "ANY",
        "openssl_version": "ANY",
        "boost_version": "ANY",
        "gtest_version": "ANY",
        "png_version": "ANY",
        "zlib_version": "ANY",
        "shared": [True, False],
        "autopilot": "ANY",
    }

    default_options = {
        "exiv2_version": "0.28.2",
        "libcurl_version": "8.6.0",
        "zlib_version":"1.2.12",
        "png_version": "1.6.38",
        "protobuf_version": "3.17.1",
        "openssl_version": "3.0.15",
        "boost_version": "1.75.0",
        "gtest_version": "1.10.0",
        "shared": True,
        "autopilot": "none",
    }

    generators = "cmake", "cmake_find_package"
    exports = "version.txt"
    exports_sources = "*", "!version.txt", "!build/"
    autopilot = None # default autopilot is None

    def __is_uavia_sdk_build(self):
        '''
        Helper function that checks whether we build using uavia-sdk
        profile or not (native build).
        '''
        sdk = self.settings.get_safe("os.sdk")
        return (sdk and "uavia-sdk" in sdk)
    
    @property
    def get_build_dependencies(self):
        """
        Allows to retrieve build dependencies depending on the autopilot.
        """
        deps = [ 
            "cmake/3.30.5",
            "ninja/1.11.0"
        ] # main build dependencies
        for autopilot in self.autopilots:
            deps.extend(autopilot.get_build_dependencies()) # extend with autopilot build dependencies
        deps = filter_dependencies(deps, self.__is_uavia_sdk_build(), ["dji", "uavia", "parrot", "dji_light"]) # filter dependencies depending on build type
        return deps
    
    @property
    def get_dependencies(self):
        """
        Allows to retrieve runtime dependencies depending on the autopilot. 
        """
        deps = [
            f"boost/{self.options.boost_version}",
            "docopt.cpp/0.6.3",
            "nlohmann_json/3.9.1",
            f"gtest/{self.options.gtest_version}",
            "uavia-ckt/1.3.23@conan/stable",
            "uavia-navtools/1.3.23@conan/stable",
            "uavia-protocol/1.3.23@conan/stable",
            "uavia-srp/1.3.23@conan/stable"
        ] # main dependencies
        for autopilot in self.autopilots:
            deps.extend(autopilot.get_build_dependencies()) # extend with autopilot build dependencies
        deps = filter_dependencies(deps, self.__is_uavia_sdk_build(), ["dji", "uavia", "parrot", "dji_light"]) # filter dependencies depending on build type
        return deps
    
    # ======================== Version control and Checks =============================

    def git(self):
        return tools.Git(folder=self.recipe_folder)

    def get_last_git_tag(self):
        try:
            return self.git().run("describe --tags --abbrev=0").lstrip("v")
        except Exception:
            return None

    def get_git_tag(self):
        try:
            return self.git().get_tag().lstrip("v")
        except Exception:
            return None

    def get_git_branch(self):
        event_name = os.getenv("GITHUB_EVENT_NAME")
        if (event_name and event_name == "pull_request"):
            return os.getenv("GITHUB_BASE_REF")
        else:
            return self.git().get_branch()

    def is_version_release(self, version):
        try:
            tools.Version(version)
        except Exception:
            return False
        return True

    def get_version_file(self):
        return open(os.path.join(self.recipe_folder, "version.txt"), "r").read().replace("\n", "").lstrip("v")

    def check_version_file(self):
        # If version is a tag with semver version X.Y.Z, version.txt file must also contain X.Y.Z
        if(self.is_version_release(self.version)):
            version_file = self.get_version_file()

            if(not self.version == version_file):
                raise Exception("version.txt file mismatch [expected : " + self.version  + "] [current : " + version_file + "]")

    # Check dependency scheme for package:
    # Package on main can only depend of uavia packages version main or "release" (=tag X.Y.Z)
    # Release package (=with a version tag) can only depend on other uavia release packages
    def check_dependencies(self):
        if self.version == "main" or self.is_version_release(self.version):
            for require, dependency in self.dependencies.items():
                if not require:
                    continue
                ref = dependency.ref
                # Check only uavia dependencies
                if not ref.name.startswith("uavia-"):
                    continue
                # main and release packages can depend of other releases
                if self.is_version_release(ref.version):
                    continue
                # packages on main can also depend on main packages
                if self.version == "main" and ref.version == "main":
                    continue
                raise Exception("invalid dependency scheme (expected release version but dependency '" + ref.name + "' has version '" + ref.version + "')")

    def get_version(self):
        version = os.getenv("UAVIA_CONAN_PROJECT_VERSION")
        if version:
            return version

        # Use the following versionning scheme:
        # - New tag is pushed on CI: tag
        # - Else: branch name, even if the current commit is tagged
        # This way, we ensure that the stable tagged versions are only built once,
        # when the tag is pushed on Github, and is not erased for instance if we trigger
        # periodically a build on the same branch

        is_github_ci_tag_ongoing = os.getenv("UAVIA_EVENT_IS_TAG") #true if CI is triggered by a new tag

        tag = self.git().get_tag()
        if tag != None and is_github_ci_tag_ongoing == "true":  
            return tag

        branch = self.get_git_branch()
        return branch
    
    # ================= The following functions are conan build steps =================
    
    def set_version(self):
        """
        Allows to set the version of the package dynamically.
        It provides an easy way to build different versions of the same project.
        """
        self.version = self.get_version()
        if os.getenv("UAVIA_CONAN_SKIP_VERSION_CHECKS"):
            return
        self.check_version_file()

    def configure(self):
        """
        Init allows to choose an autopilot to build project for.
        """
        autopilots = str(self.options.autopilot).split(",")

        if autopilots:
            self.autopilots = []
            for autopilot in autopilots:
                self.handle_single_autopilot(autopilot)
        else:
            print("No autopilots were specified")
            sys.exit(1)            

        print("--------------> Size of the list:", len(autopilots))
        self.options["boost"].without_python = True

    def handle_single_autopilot(self, autopilot_name):

        if autopilot_name == "dji":
            self.autopilots.append(DJIAutopilot())
        elif autopilot_name == "dji_light":
            self.autopilots.append(DJILightAutopilot())
        elif autopilot_name == "parrot":
            self.autopilots.append(ParrotAutopilot())
        elif autopilot_name == "ardupilot":
            self.autopilots.append(Autopilot())
        elif autopilot_name == "ardurover":
            self.autopilots.append(Autopilot())
        elif autopilot_name == "none":
            self.autopilots.append(Autopilot())
        else:
            print("Autopilot " + str(self.options.autopilot) + " is unknown")
            sys.exit(1)

    def validate(self):
        """
        Allows to check dependencies if version checks are activated (not skipped).
        Scans dependencies to see if they are stable
        """
        if os.getenv("UAVIA_CONAN_SKIP_VERSION_CHECKS"):
            return
        self.check_dependencies()

    def export(self):
        self.copy("*.py", src="conf", dst="conf") # copy conf files to make them a part of the recipe

    def build_requirements(self):
        """
        Build requirements for the project (conan config).
        """
        for dependency in self.get_build_dependencies:
            self.build_requires(dependency)

        if not self.__is_uavia_sdk_build():
            if str(self.options.protobuf_version) != "none":
                self.build_requires("protobuf/" + str(self.options.protobuf_version))

    def requirements(self):
        """
        Runtime requirements for the project (conan config).
        """
        for dependency in self.get_dependencies:
            self.requires(dependency)
        if not self.__is_uavia_sdk_build():
            if str(self.options.protobuf_version) != "none":
                self.requires("protobuf/" + str(self.options.protobuf_version))
            if str(self.options.zlib_version) != "none":
                self.requires(f"zlib/{self.options.zlib_version}")
            if str(self.options.openssl_version) != "none":
                self.requires(f"openssl/{self.options.openssl_version}")
            if str(self.options.exiv2_version) != "none":
                self.requires(f"exiv2/{self.options.exiv2_version}")
            if str(self.options.libcurl_version) != "none":
                self.requires(f"libcurl/{self.options.libcurl_version}")
            if self.options.png_version.value != "none":
                self.requires("libpng/" + self.options.png_version.value)

    # ================= Conan build steps =================

    def configure_cmake(self):   
        cmake = CMake(self, generator="Ninja")
        autopilots = str(self.options.autopilot).split(",")
        print("autopilots: ", autopilots)
        for autopilot in autopilots:
            if autopilot == "dji":
                cmake.definitions["AGI_DJI_SUPPORT"] = "TRUE"
            elif autopilot == "dji_light":
                cmake.definitions["AGI_DJI_LIGHT_SUPPORT"] = "TRUE"
            elif autopilot == "parrot":
                cmake.definitions["AGI_PARROT_SUPPORT"] = "TRUE"
            elif autopilot == "ardupilot":
                cmake.definitions["AGI_ARDUPILOT_SUPPORT"] = "TRUE"
            elif autopilot == "ardurover":
                cmake.definitions["AGI_ARDUROVER_SUPPORT"] = "TRUE"
            elif autopilot == "none":
                cmake.definitions["AGI_DJI_SUPPORT"] = "FALSE"
                cmake.definitions["AGI_PARROT_SUPPORT"] = "FALSE"
                cmake.definitions["AGI_ARDUPILOT_SUPPORT"] = "FALSE"
                cmake.definitions["AGI_ARDUROVER_SUPPORT"] = "FALSE"

        cmake.definitions["CMAKE_VERBOSE_MAKEFILE"] = "ON"
        cmake.definitions["CONAN_CMAKE_BUILD_MODE"] = "ON"
        
        # Use C++ standard from Conan settings (cppstd=17 from profile)
        if self.settings.get_safe("cppstd"):
            cmake.definitions["CMAKE_CXX_STANDARD"] = str(self.settings.cppstd)
            cmake.definitions["CMAKE_CXX_STANDARD_REQUIRED"] = "ON"
        
        # Disable CMake internal curl test to avoid OpenSSL conflicts with Parrot SDK
        cmake.definitions["CMAKE_USE_SYSTEM_CURL"] = "ON" 
        cmake.definitions["BUILD_CURL_TESTS"] = "OFF"
        cmake.definitions["CURL_DISABLE_TESTS"] = "ON"
        print("cmake.definitions: ", cmake.definitions)
        cmake.configure()
        return cmake

    def build(self):
        cmake = self.configure_cmake()
        cmake.build()

        if os.getenv("RUN_TESTS", "false").lower() == "true":
            env_build = tools.RunEnvironment(self)
            with tools.environment_append(env_build.vars):
                # This will run the executable with the appropriate environment variables set
                self.run("ctest --timeout 900 --output-on-failure")
        else:
            self.output.info("Skipping tests, RUN_TESTS is not set or is false.")

    def test(self):
        cmake = self.configure_cmake()
        cmake.test(output_on_failure=True)

    def package(self):
        cmake = self.configure_cmake()
        cmake.build(target="install/strip")
        self.copy("COPYING", "licenses")
