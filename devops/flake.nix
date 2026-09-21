# SPDX-License-Identifier: MIT
# AV2 / xHE-AAC converter development environment (Nixpkgs 25.05).
{
  description = "Desktop GUI that transcodes video to AV2 and audio to xHE-AAC";

  nixConfig = {
    extra-experimental-features = "nix-command flakes";
  };

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";

    avm = {
      url = "github:AOMediaCodec/avm/v1.0.0";
      flake = false;
    };
    dav2d-av2 = {
      url = "github:afen261/dav2d-av2";
      flake = false;
    };
    vlc-av2-src = {
      url = "github:afen261/vlc-av2";
      flake = false;
    };
    exhale-src = {
      url = "gitlab:ecodis/exhale";
      flake = false;
    };
    av2-tools-src = {
      url = "github:AOMediaCodec/av2-tools";
      flake = false;
    };
    cli11 = {
      url = "github:CLIUtils/CLI11/v2.5.0";
      flake = false;
    };
    spdlog = {
      url = "github:gabime/spdlog/v1.14.1";
      flake = false;
    };
    nlohmann_json = {
      url = "github:nlohmann/json/v3.11.3";
      flake = false;
    };
    isobmff = {
      url = "github:MPEGGroup/isobmff";
      flake = false;
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      avm,
      dav2d-av2,
      vlc-av2-src,
      exhale-src,
      av2-tools-src,
      cli11,
      spdlog,
      nlohmann_json,
      isobmff,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      projectRoot = toString ../.;
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = import nixpkgs {
            inherit system;
            config.allowUnfree = true;
          };
          avmPkg = pkgs.callPackage ./pkgs/avm.nix { src = avm; };
          dav2dPkg = pkgs.callPackage ./pkgs/dav2d-av2.nix { src = dav2d-av2; };
          exhalePkg = pkgs.callPackage ./pkgs/exhale.nix { src = exhale-src; };
          av2ToolsPkg = pkgs.callPackage ./pkgs/av2-tools.nix {
            src = av2-tools-src;
            cli11Src = cli11;
            spdlogSrc = spdlog;
            nlohmannJsonSrc = nlohmann_json;
            isobmffSrc = isobmff;
          };
          vlcPkg =
            if pkgs.stdenv.isLinux then
              pkgs.callPackage ./pkgs/vlc-av2.nix {
                src = vlc-av2-src;
                dav2d-av2 = dav2dPkg;
              }
            else
              null;
          web = import ./shell.nix {
            inherit pkgs;
            lib = pkgs.lib;
            inherit projectRoot;
            avm = avmPkg;
            dav2d-av2 = dav2dPkg;
            exhale = exhalePkg;
            av2-tools = av2ToolsPkg;
            vlc-av2 = vlcPkg;
          };
        in
        {
          default = web.converter;
          av2-converter = web.converter;
          avm = avmPkg;
          dav2d-av2 = dav2dPkg;
          exhale = exhalePkg;
          av2-tools = av2ToolsPkg;
        }
        // pkgs.lib.optionalAttrs (vlcPkg != null) { vlc-av2 = vlcPkg; }
      );

      devShells = forAllSystems (
        system:
        let
          pkgs = import nixpkgs {
            inherit system;
            config.allowUnfree = true;
          };
          avmPkg = pkgs.callPackage ./pkgs/avm.nix { src = avm; };
          dav2dPkg = pkgs.callPackage ./pkgs/dav2d-av2.nix { src = dav2d-av2; };
          exhalePkg = pkgs.callPackage ./pkgs/exhale.nix { src = exhale-src; };
          av2ToolsPkg = pkgs.callPackage ./pkgs/av2-tools.nix {
            src = av2-tools-src;
            cli11Src = cli11;
            spdlogSrc = spdlog;
            nlohmannJsonSrc = nlohmann_json;
            isobmffSrc = isobmff;
          };
          vlcPkg =
            if pkgs.stdenv.isLinux then
              pkgs.callPackage ./pkgs/vlc-av2.nix {
                src = vlc-av2-src;
                dav2d-av2 = dav2dPkg;
              }
            else
              null;
          web = import ./shell.nix {
            inherit pkgs;
            lib = pkgs.lib;
            inherit projectRoot;
            avm = avmPkg;
            dav2d-av2 = dav2dPkg;
            exhale = exhalePkg;
            av2-tools = av2ToolsPkg;
            vlc-av2 = vlcPkg;
          };
        in
        {
          default = web.shell;
        }
      );

      formatter = forAllSystems (system: nixpkgs.legacyPackages.${system}.nixfmt-rfc-style);
    };
}
