## Community Bonding Period

### [Github Repo](https://gitter.im/pallavagarwal07/SummerOfCode16)

---

#### Meeting 1: May 9th

* __Things done till now__:
  1. Understand source code of tatt and eix.
  2. Set up a BOINC project using given sample applications.
     Talked to BOINC developers regarding setup problems.
  3. Look into the source code of gentoo-bb and talk to one of its contributors.
* __Things to do__:
  4. Figure out a way to get docker to work on the client side of 
     BOINC (maybe with developers’ help).
  5. Get in touch with more of Gentoo Community.

---

#### Meeting 2: May 16th

* __Things to be discussed__:
  1. EAPI discussions proposal: Adding a post_install test script in the ebuild.
     To be proposed for EAPI 7 / Any other method ---?
  2. Using Docker inside docker instead of docker installed by BOINC client:
     Instead of the client downloading and installing docker
     (which would cause problems dependent on OS and package manager), a docker
     image containing only BOINC client and DOCKER installed should be used. For
     stabilization, docker containers inside the main docker container should be used.
  3. USE flag combinations: [SAT-Solver for REQ_USE](
     https://github.com/pallavagarwal07/SummerOfCode16/blob/master/satsolver/solver.py)
  4. Resources to learn Portage API??
* __TODO__:
  1. Compare Docker { Client + Docker { container (s) } }
     vs Docker { Client } + Docker { container (s) } DONE
  2. Check out docker-compose DONE
  3. Maybe check rkt (after trying all of the above)
  4. Continue discussion about EAPI upgrade vs. separate scripts especially with package manager maintainers
  5. Try REST api of Bugzilla DONE
  6. Find out how to use Portage API DONE (A LITTLE)  or Gentoolkit API

---


#### Meeting 3: May 23rd

* __Things to be discussed__:
  1. Bug stabilization automation (server side) see repo for interaction with BUGZILLA
  2. Docker problems
  3. Coding Period begins
  4. Create tasks on github
  5. Communicate with package maintainers

---
---
---

## Coding Period

#### Meeting 4: May 31st

* __Things to be discussed__:
  1. Testing of build server prototype
  2. Maybe use portage APIs to build DAG instead of calling emerge?
* __TODO__:
  1. Draw diagrams for Client/Server workflow
  2. Have some usage examples for testing by other people

---

#### Meeting 5: June 6th

* __Things to be discussed__:
  1. Wrapper script for easy testing
  2. Reminder: Server with docker installed?
  3. How to automate email sending?
  4. Package caching, frequency of docker image update?

