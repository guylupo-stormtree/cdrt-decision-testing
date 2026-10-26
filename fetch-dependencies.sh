#!/bin/sh
# Fetch the two pinned dependencies of this repository, and nothing deeper:
#   vendor/proofweave-decision-assurance   ProofWeave at the pinned tag
#   .../vendor/RepoAudit                   RepoAudit at the pinned commit (its own benchmark submodules,
#                                          large third-party C/C++/Go projects, are not needed and not fetched)
set -e
cd "$(dirname "$0")"
git submodule update --init vendor/proofweave-decision-assurance
git -C vendor/proofweave-decision-assurance submodule update --init vendor/RepoAudit
echo "ProofWeave: $(git -C vendor/proofweave-decision-assurance describe --tags)"
echo "RepoAudit:  $(git -C vendor/proofweave-decision-assurance/vendor/RepoAudit rev-parse --short HEAD)"
