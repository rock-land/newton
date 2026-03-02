# claude-bootstrap REVISIONS

## stage-init
Add a /stage-init command. prompt the user to run the stage-init command and make sure tasks can't be run if the stage-init command hasn't been run for that stage yet (or ask if the stage-init command should be run)

handles the full stage initialization ceremony:                                                           
1. Prerequisite checks — verifies previous stage is APPROVED in REVIEWS.md                                                                                
2. Task list promotion — reads backlog for next stage, fills in scope + acceptance criteria from SPEC.md, proposes all relevant tasks to complete a stage as well as a stage gate task                        
3. User approval — presents the full stage definition and waits for sign-off                                                                              
4. TASKS.md update — creates the stage section and tasks, update backlog. backlog
5. Branch creation — git checkout -b stage/{N}-{name} from main
6. VERSION init — sets 0.{STAGE}.0
7. Commit + push — commits the setup to the stage branch

## stage-report
For the run stage-report command it should be done with by interviewing me in detail using the AskUserQuestion tool.

And keep interviewing until we've covered everything, updating the tasks for stage and suggesting the next course of action.

after stage-report has remediation tasks:

fixes should be added to the TASKS.md at the end of the relevant stage with an additional suffix (eg. -FIXn).

instead of running a complete review, red-review and stage-report cycle again (this could go on forever) we should add a command (/verify-fixes) that just reviews that any remediation tasks were successfully completed and didn't introduce any new problems.

## tasks

When tasks get added later the ID's are all out of order. Task naming is a bit confusing eg, T-0nn for stage 1 tasks, T-1nn for stage 2 tasks. these should be more consistent to reflect tasks (T-1nn for stage 1, T-2nn for stage 2 tasks and so on). 

The backlog should just include the planned Stage name and number. Instead of backlog tasks getting generated early on these should only be generated on stage initialization (see stage-init). If it's more useful to have a small summary of the stage then that's ok (for instance it could be useful to name / outline the client and server work - then again, that may be unecessary).

at the end of each task suggest I run /compact before commmencing the next task. in addition to that suggest I run /clean at the end of each stage.

when running the task for fixes all fix tasks should be run batched together instead of one by one. only explicitly alert if there are particular tasks should be run, tested and verified separately. But for the most part, small bug fixes can be batched together. 

update to the task command to make it smart enough to figure out the next task on its own:
If no argument is provided, find the first task with status TODO and execute it.
If an argument is provided, find the task matching "$ARGUMENTS" and attempt to execute it (continuing with required checks etc)
Then you just type /task with no arguments and it picks up the next one automatically — no autocomplete needed.

## project-status
add a /project-status command listing: 
- current stage
- next steps (task, review etc)
- last task / next task

## user acceptance tests
create a file in the root of the project called UAT.md - using the TASKS.md for reference create a list of user acceptance tests for the stage for user to test the app against to ensure each feature works as expected. these should be presented in a table with a checkbox, the test  and a notes. include any extra you think will be useful for testers to know and that would help communicate back to the developer. Update the process so the UAT.md is updated at the end of each stage to cover all relevant functionality completed in the stage.

## readme
add README update directive to the end of each stage process. update the relevant commands to review and update (or create) the project README.md file on stage each completion using best practices for writing a high quality and useful README file

## dev journal
create a file in the root of the project called JOURNAL.md
a history of all prompts / commands etc
date time, stage / task, command and one sentance summary of what was exectuted OR one sentance summary of prompt
sorted by date / time descending (should see most recent at top of file)
gets updated for every cli usage except system commands (like /clear, /context, /compact, /status etc)

## existing project bootstrap
a process or command to bootstrap an existing project - in this situation the bootstrap project files will be copied into the project and then claude code will need to review the project and update the commands, CLAUDE.md, DECISIONS.md, REVIEWS.md and TASKS.md so the development can continue with claude code. since it's mid project it doesn't need to retroactively create stages and tasks, but can log a summary of the project in the TASKS.md file of the completed work to date. Note the first stage in this situation could be addressing any issues found before commencing with new feature development.

## bash
if you can't find a bash command needed to run, you should pause and ask the user what they want to do? install, cancel etc. i have noticed sometimes scripts getting written to work around the absence of certain command line programs - if theres a program that exists that will do the job, alert the user that they should install it etc.
