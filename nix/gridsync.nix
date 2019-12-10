{ python3Packages
, fetchFromGitHub
, gnumake
, wrapQtAppsHook
, xvfb_run
, autobahn
, humanize
, hyperlink
, magic-wormhole
, pynacl
, pyqt5
, pyyaml
, qt5reactor
, treq
, twisted
, txtorcon
, zxcvbn
, atomicwrites
, distro
, tahoe-lafs

, tox
, pytest
, pytestcov
, pytesttwisted
, pytestqt
}:
python3Packages.buildPythonApplication rec {
  version = "v0.4.2.dev";
  pname = "gridsync";
  name = "${pname}-${version}";
  src = ../.;

  nativeBuildInputs = [
    wrapQtAppsHook
  ];

  buildInputs = pythonPath ++ [
    tahoe-lafs
  ];

  # pythonPath is deprecated but setting it is the only way to get run-time
  # dependencies injected by the wrapper generated by buildPythonApplication!
  pythonPath = [
    atomicwrites
    autobahn
    distro
    humanize
    hyperlink
    magic-wormhole
    pynacl
    pyqt5
    pyyaml
    qt5reactor
    treq
    twisted
    twisted.extras.tls
    txtorcon
    zxcvbn
  ];

  checkInputs = [
    tox
    pytest
    pytestcov
    pytesttwisted
    pytestqt
    xvfb_run
  ];

  # Wrap it ourselves because non-ELF executables are ignored by the automatic
  # wrapping logic.  Do this in postFixup so that the Nixpkgs Python support
  # can do the Python wrapping.  wrapProgram replaces the Python script with a
  # shell script which won't be recognized by wrapPythonPrograms, I suppose.
  postFixup = ''
    wrapProgram "$out/bin/gridsync" "''${qtWrapperArgs[@]}"
  '';

  doCheck = false;

  # checkPhase = ''
  # ${xvfb_run}/bin/xvfb-run -a pytest tests
  # '';
}
