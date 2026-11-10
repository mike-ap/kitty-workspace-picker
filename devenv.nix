{ pkgs, ... }:

{
  packages = [
    pkgs.direnv
    pkgs.just
    pkgs.lefthook
    pkgs.shellcheck
    pkgs.shfmt
    pkgs.markdownlint-cli2
  ];

  enterShell = ''
    if [ -e .git ]; then
      lefthook install
    fi
  '';

  languages.python = {
    enable = true;
    package = pkgs.python312;
    venv.enable = true;
    uv = {
      enable = true;
      sync.enable = true;
    };
  };
}
