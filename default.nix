{ nixpkgs ? import <nixpkgs> {  } }:

let
  pkgs = with nixpkgs; [
    iproute2
    python312Packages.kubernetes
    python312Packages.netifaces
  ];

in
  nixpkgs.stdenv.mkDerivation {
    name = "env";
    buildInputs = pkgs;
  }
