import os

# 0.1.37: the git guard runs commands on a copy of the repository by default. Most tests drive the guard with a scripted
# model and check its logic; the copy would replace those scripted answers with git's own. They run with the copy off;
# the tests of the copy (test_git_sim.py) turn it on explicitly (simulate=True).
os.environ.setdefault("EKBASIS_GIT_COPY", "0")
