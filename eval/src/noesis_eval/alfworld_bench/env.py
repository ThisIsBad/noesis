"""Minimal text-based environment that mirrors ALFWorld's contract.

Each ``Task`` is a deterministic state-machine: the agent receives the
goal + observation, issues a textual action, and the env returns the
next observation, a reward, and a ``done`` flag. ``inject_failure_at``
forces the env to return a failure for a specific step index, used to
benchmark backtrack-recovery.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Task:
    task_id: str
    goal: str
    initial_observation: str
    canonical_plan: tuple[str, ...]
    # Step index (0-based) at which the env should reject the canonical
    # action and demand an alternative. None disables injection.
    inject_failure_at: Optional[int] = None
    # Alternative actions accepted at the failure index. Empty tuple =
    # no recovery is possible (the episode will fail).
    recovery_actions: tuple[str, ...] = ()


@dataclass
class StepResult:
    observation: str
    reward: float
    done: bool
    info: dict[str, object] = field(default_factory=dict)


class MockAlfworldEnv:
    """In-memory deterministic env. One env instance per task.

    Contract mirrors ALFWorld's textworld interface:
        env.reset() -> observation: str
        env.step(action: str) -> StepResult
    """

    def __init__(self, task: Task) -> None:
        self.task = task
        self._cursor: int = 0
        self._injected_recovered: bool = False
        self._done: bool = False

    def reset(self) -> str:
        self._cursor = 0
        self._injected_recovered = False
        self._done = False
        return f"Goal: {self.task.goal}\n{self.task.initial_observation}"

    def step(self, action: str) -> StepResult:
        if self._done:
            raise RuntimeError("step() called after episode terminated")

        action = action.strip().lower()
        plan = self.task.canonical_plan
        idx = self._cursor

        # Failure injection: at the marked index, reject the canonical
        # action and force the agent to use a recovery action instead.
        injecting = (
            self.task.inject_failure_at == idx
            and not self._injected_recovered
        )
        if injecting:
            if action in {a.lower() for a in self.task.recovery_actions}:
                self._injected_recovered = True
                self._cursor += 1
                done = self._cursor >= len(plan)
                self._done = done
                return StepResult(
                    observation=f"Recovered. Next: {self._next_hint()}",
                    reward=1.0 if done else 0.0,
                    done=done,
                    info={"recovered": True},
                )
            options = list(self.task.recovery_actions) or ["(no recovery)"]
            return StepResult(
                observation=(
                    f"Action '{action}' failed. Try one of: {options}"
                ),
                reward=-1.0,
                done=False,
                info={"failed": True, "step": idx},
            )

        if idx < len(plan) and action == plan[idx].lower():
            self._cursor += 1
            done = self._cursor >= len(plan)
            self._done = done
            return StepResult(
                observation=(
                    f"Done. Goal '{self.task.goal}' achieved."
                    if done
                    else f"OK. Next: {self._next_hint()}"
                ),
                reward=1.0 if done else 0.0,
                done=done,
            )

        return StepResult(
            observation=f"Action '{action}' is not valid here.",
            reward=-1.0,
            done=False,
            info={"failed": True, "step": idx},
        )

    def _next_hint(self) -> str:
        if self._cursor >= len(self.task.canonical_plan):
            return "(complete)"
        return self.task.canonical_plan[self._cursor]


def build_default_suite() -> list[Task]:
    """Five hand-built tasks covering the success / failure / recovery axes.

    Two clean tasks (no injection), two with recoverable failures, one
    with an unrecoverable failure. Lets a runner exercise both nominal
    success rate and backtrack-recovery rate from a single suite.
    """
    return [
        Task(
            task_id="t1_apple_to_fridge",
            goal="put the apple in the fridge",
            initial_observation=(
                "You are in the kitchen. A table holds an apple. "
                "A closed fridge is nearby."
            ),
            canonical_plan=(
                "pick up apple",
                "open fridge",
                "put apple in fridge",
                "close fridge",
            ),
        ),
        Task(
            task_id="t2_book_to_shelf",
            goal="place the book on the shelf",
            initial_observation=(
                "You are in the study. A book lies on the desk. "
                "An empty shelf is on the wall."
            ),
            canonical_plan=(
                "pick up book",
                "walk to shelf",
                "place book on shelf",
            ),
        ),
        Task(
            task_id="t3_recover_locked_drawer",
            goal="retrieve the key from the drawer",
            initial_observation=(
                "You are in the office. A drawer is locked. A "
                "paperclip lies on the floor."
            ),
            canonical_plan=(
                "open drawer",
                "take key from drawer",
            ),
            inject_failure_at=0,
            recovery_actions=(
                "pick up paperclip",
                "pick paperclip and unlock drawer",
            ),
        ),
        Task(
            task_id="t4_recover_blocked_path",
            goal="reach the exit",
            initial_observation=(
                "You are in a hallway. A box blocks the door. "
                "An alternative side passage is visible."
            ),
            canonical_plan=(
                "walk through door",
                "exit building",
            ),
            inject_failure_at=0,
            recovery_actions=("take side passage",),
        ),
        Task(
            task_id="t5_unrecoverable_locked_room",
            goal="enter the vault",
            initial_observation=(
                "You are in a corridor. The vault door requires a "
                "biometric scan you cannot pass."
            ),
            canonical_plan=("open vault",),
            inject_failure_at=0,
            recovery_actions=(),
        ),
    ]


# ── Stage-3 acceptance suite (50 injected step-failures) ─────────────────────
#
# Every task injects exactly one step-failure at index 0, so across the suite
# `sum(failures_seen) == 50` — matching the ROADMAP's "50 injizierten
# Step-Failures" target for Praxis backtrack-recovery. 45 failures are
# recoverable with the single hinted alternative; 5 are unrecoverable sinks
# (biometric / expired / permission-denied) that keep the success rate
# honest.


def _recoverable(
    task_id: str,
    goal: str,
    initial_observation: str,
    canonical_plan: tuple[str, ...],
    recovery: tuple[str, ...],
) -> Task:
    return Task(
        task_id=task_id,
        goal=goal,
        initial_observation=initial_observation,
        canonical_plan=canonical_plan,
        inject_failure_at=0,
        recovery_actions=recovery,
    )


def _unrecoverable(
    task_id: str,
    goal: str,
    initial_observation: str,
    canonical_plan: tuple[str, ...],
) -> Task:
    return Task(
        task_id=task_id,
        goal=goal,
        initial_observation=initial_observation,
        canonical_plan=canonical_plan,
        inject_failure_at=0,
        recovery_actions=(),
    )


def build_stage3_suite() -> list[Task]:
    """50-task acceptance suite for Praxis Stage-3 backtrack-recovery.

    Organised into five themes of ten tasks (kitchen, office, workshop,
    library, lab). Within each theme, nine tasks are recoverable with a
    single alternative action and one is an unrecoverable dead-end. A
    planner hitting the reference plans + recoveries lands at ~90%
    success and 90% backtrack-recovery against the 50 injected failures.
    """
    return [
        # ── Kitchen ──────────────────────────────────────────────────────────
        _recoverable(
            "k1_stuck_fridge",
            "put the leftovers in the fridge",
            "The fridge door is stuck shut. A rag is draped over the handle.",
            ("open fridge", "place leftovers on shelf", "close fridge"),
            ("pull handle firmly with rag",),
        ),
        _recoverable(
            "k2_missing_peeler",
            "peel the potato for dinner",
            "A potato sits on the board. The peeler drawer is jammed.",
            ("peel potato", "rinse potato"),
            ("use paring knife from block",),
        ),
        _recoverable(
            "k3_empty_kettle",
            "make tea in the kitchen",
            "Kettle is empty. A filled water pitcher stands by the sink.",
            ("boil kettle", "pour water into mug", "steep teabag"),
            ("fill kettle from pitcher",),
        ),
        _recoverable(
            "k4_burner_off",
            "simmer the stew on the stove",
            "The pot is on a cold burner; a gas valve is shut downstream.",
            ("turn on burner", "stir stew", "lower flame"),
            ("open gas valve",),
        ),
        _recoverable(
            "k5_locked_pantry",
            "grab the sugar from the pantry",
            "The pantry door is locked. A key ring hangs by the fridge.",
            ("open pantry", "take sugar from pantry"),
            ("take key from ring and unlock pantry",),
        ),
        _recoverable(
            "k6_dull_knife",
            "slice the tomato for the salad",
            "The slicing knife is too dull to cut cleanly. "
            "A sharpener is in the drawer.",
            ("slice tomato", "place slices on plate"),
            ("sharpen knife on rod",),
        ),
        _recoverable(
            "k7_crowded_sink",
            "wash the mixing bowl",
            "The sink is full of dirty dishes. A dish rack is nearby.",
            ("rinse bowl in sink", "dry bowl with towel"),
            ("move dishes to rack",),
        ),
        _recoverable(
            "k8_tripped_breaker",
            "blend the smoothie",
            "The blender is plugged in but unresponsive. "
            "The breaker panel is in the hall.",
            ("press blend button", "pour smoothie into glass"),
            ("reset breaker in hall panel",),
        ),
        _recoverable(
            "k9_oven_preheat",
            "bake the bread",
            "The oven is cold. Dough is on the counter, ready.",
            ("place dough in oven", "start 30 minute timer"),
            ("preheat oven to 220C",),
        ),
        _unrecoverable(
            "k10_expired_yeast",
            "bake the sourdough",
            "The only yeast packet is two years past expiry; no starter is available.",
            ("mix dough with yeast",),
        ),
        # ── Office ───────────────────────────────────────────────────────────
        _recoverable(
            "o1_locked_drawer",
            "retrieve the budget folder from the drawer",
            "The desk drawer is locked. A paperclip lies on the floor.",
            ("open drawer", "take folder from drawer"),
            ("pick paperclip and unlock drawer",),
        ),
        _recoverable(
            "o2_jammed_printer",
            "print the quarterly report",
            "The printer flashes a paper-jam warning. A spare toner sits on the shelf.",
            ("print report", "collect pages from tray"),
            ("clear jam from rear tray",),
        ),
        _recoverable(
            "o3_dead_laptop",
            "email the contract to legal",
            "The laptop battery is flat. A charger is under the desk.",
            ("open email client", "send contract to legal"),
            ("plug in charger",),
        ),
        _recoverable(
            "o4_no_projector_cable",
            "start the standup on the projector",
            "The projector has no HDMI cable connected. "
            "A cable lies coiled on the shelf.",
            ("power on projector", "share screen"),
            ("connect HDMI cable to projector",),
        ),
        _recoverable(
            "o5_muted_mic",
            "join the conference call",
            "The microphone is hardware-muted; a switch is on the cable.",
            ("unmute mic", "greet participants"),
            ("flip cable mute switch",),
        ),
        _recoverable(
            "o6_missing_stamp",
            "mail the signed agreement",
            "You have the envelope ready but no stamps. "
            "A petty-cash box is behind you.",
            ("affix stamp", "drop letter in box"),
            ("buy stamp from petty cash",),
        ),
        _recoverable(
            "o7_offline_vpn",
            "access the shared drive",
            "The VPN client shows 'disconnected'. The token generator is in your bag.",
            ("open shared drive", "download report"),
            ("reconnect VPN with token",),
        ),
        _recoverable(
            "o8_locked_cabinet",
            "file the expense receipts",
            "The filing cabinet is locked. The ledger room holds the spare key.",
            ("open cabinet", "file receipts in section F"),
            ("fetch spare key from ledger room",),
        ),
        _recoverable(
            "o9_full_shredder",
            "shred the obsolete NDAs",
            "The shredder bin is full and the motor has cut out.",
            ("shred documents", "bag the shreddings"),
            ("empty shredder bin into recycling",),
        ),
        _unrecoverable(
            "o10_revoked_access",
            "archive the client records",
            "Your account was revoked at 09:00 and no admin is on call.",
            ("open records system",),
        ),
        # ── Workshop ─────────────────────────────────────────────────────────
        _recoverable(
            "w1_dead_drill",
            "drill the pilot hole",
            "The cordless drill is dead; a charged spare battery is on the bench.",
            ("drill pilot hole", "widen hole for screw"),
            ("swap drill battery",),
        ),
        _recoverable(
            "w2_wrong_bit",
            "drive the lag screw",
            "The bit in the chuck is a Phillips head but the screw is Torx.",
            ("drive screw", "tighten screw"),
            ("swap to Torx T25 bit",),
        ),
        _recoverable(
            "w3_loose_vise",
            "clamp the dowel to the bench",
            "The vise jaws slip — the lead-screw handle has worked loose.",
            ("clamp dowel", "mark drill line"),
            ("tighten vise handle",),
        ),
        _recoverable(
            "w4_no_compressor",
            "nail the trim to the moulding",
            "The nailer is connected but the compressor is off.",
            ("fire nailer", "verify flush with trim"),
            ("switch on compressor",),
        ),
        _recoverable(
            "w5_blunt_saw",
            "cut the 2x4 to length",
            "The circular saw blade is blunt; a sharp spare hangs on the wall.",
            ("cut board at mark", "deburr edge with file"),
            ("swap circular saw blade",),
        ),
        _recoverable(
            "w6_dust_in_slide",
            "open the tool chest bottom drawer",
            "The bottom drawer slide is clogged with sawdust.",
            ("open bottom drawer", "retrieve chisel set"),
            ("blow dust from slide",),
        ),
        _recoverable(
            "w7_tangled_extension",
            "power the bandsaw in the far corner",
            "The orange extension cord is a tangled snarl on the floor.",
            ("plug in bandsaw", "run test cut"),
            ("untangle extension cord",),
        ),
        _recoverable(
            "w8_oiled_clamp",
            "glue-up the mitred box",
            "The clamp pads are oily from last week's finish — glue will skid.",
            ("apply clamps to joint", "wipe glue squeeze-out"),
            ("wipe clamp pads with solvent",),
        ),
        _recoverable(
            "w9_missing_earplugs",
            "run the planer to flatten the board",
            "Shop rules forbid running the planer without hearing protection.",
            ("start planer", "feed board through"),
            ("fetch earplugs from PPE station",),
        ),
        _unrecoverable(
            "w10_stripped_bolt",
            "disassemble the seized fixture",
            "The retaining bolt is fully stripped and welded by corrosion; "
            "no extractor on-site.",
            ("remove retaining bolt",),
        ),
        # ── Library ──────────────────────────────────────────────────────────
        _recoverable(
            "l1_reference_locked",
            "consult the reference atlas",
            "The reference cabinet is locked outside open hours. "
            "The desk librarian holds the key.",
            ("open reference cabinet", "read atlas index"),
            ("ask librarian for cabinet key",),
        ),
        _recoverable(
            "l2_misshelved_volume",
            "find volume IV of the city histories",
            "Volume IV is not in its slot; a stack of returns sits on the cart.",
            ("take volume IV from shelf", "check out volume IV"),
            ("search returns cart",),
        ),
        _recoverable(
            "l3_broken_catalog_pc",
            "look up the Dewey code for oral histories",
            "The catalog PC is frozen on a blue screen.",
            ("search catalog for oral history", "note Dewey code"),
            ("reboot catalog PC",),
        ),
        _recoverable(
            "l4_expired_card",
            "check out the illustrated folio",
            "Your library card expired last month.",
            ("scan card at desk", "carry folio home"),
            ("renew card at front desk",),
        ),
        _recoverable(
            "l5_loud_atrium",
            "record an audio summary of the article",
            "The atrium is too loud for a clean recording.",
            ("start voice recorder", "dictate article summary"),
            ("move to quiet study room",),
        ),
        _recoverable(
            "l6_torn_map",
            "trace the river route on the county map",
            "The only copy of the map has a torn section across the river.",
            ("unfold map on table", "trace route with pencil"),
            ("tape map at counter",),
        ),
        _recoverable(
            "l7_wrong_edition",
            "cite the 3rd edition of the manual",
            "Only the 1st edition is on the open stacks; the 3rd lives in storage.",
            ("pull manual from shelf", "copy citation block"),
            ("request edition 3 from storage",),
        ),
        _recoverable(
            "l8_no_paper",
            "print the archival index card",
            "The printer has paper jammed and an empty paper tray.",
            ("print index card", "staple card to envelope"),
            ("refill paper tray",),
        ),
        _recoverable(
            "l9_expired_scanner_license",
            "scan the contract to PDF",
            "The scanner software complains about a lapsed license.",
            ("scan document", "save PDF to drive"),
            ("activate license with admin code",),
        ),
        _unrecoverable(
            "l10_sealed_archive",
            "read the 1912 municipal minutes",
            "The archive box is permanently sealed until 2050 by donor "
            "clause; no override available.",
            ("open archive box",),
        ),
        # ── Lab ──────────────────────────────────────────────────────────────
        _recoverable(
            "b1_fume_hood_off",
            "run the titration at the bench",
            "The fume hood is closed and the fan is off.",
            ("begin titration", "record endpoint"),
            ("raise sash and start fan",),
        ),
        _recoverable(
            "b2_uncalibrated_balance",
            "weigh the sample for HPLC",
            "The analytical balance is uncalibrated since Monday.",
            ("tare balance", "weigh 50 mg sample"),
            ("calibrate balance with 100 mg mass",),
        ),
        _recoverable(
            "b3_cold_incubator",
            "culture the cells overnight",
            "The incubator display reads 25 C — set-point was lost.",
            ("place plates in incubator", "start 16 hour timer"),
            ("set incubator to 37 C",),
        ),
        _recoverable(
            "b4_centrifuge_unbalanced",
            "spin down the supernatants",
            "The centrifuge aborted: rotor is unbalanced with one tube.",
            ("start centrifuge", "decant supernatant"),
            ("add counterbalance tube",),
        ),
        _recoverable(
            "b5_empty_n2",
            "freeze the biopsy samples",
            "The liquid nitrogen dewar is empty.",
            ("immerse cryovials", "store in freezer"),
            ("refill dewar from bulk tank",),
        ),
        _recoverable(
            "b6_bad_pipette_tip",
            "aliquot the buffer into 96 wells",
            "The pipette tip dribbles — rubber seal is cracked.",
            ("aspirate buffer", "dispense into wells"),
            ("replace pipette tip",),
        ),
        _recoverable(
            "b7_stale_reagent",
            "run the Bradford assay",
            "The Bradford reagent bottle is past its shelf life.",
            ("mix reagent with sample", "read absorbance at 595 nm"),
            ("open fresh reagent bottle",),
        ),
        _recoverable(
            "b8_no_gloves",
            "handle the carcinogen stock",
            "Nitrile gloves are out; a spare box sits in the stockroom.",
            ("transfer stock to vial", "label vial with hazard sticker"),
            ("fetch gloves from stockroom",),
        ),
        _recoverable(
            "b9_gas_cylinder_shut",
            "purge the chromatography column",
            "The argon cylinder main valve is closed.",
            ("purge column", "equilibrate solvent"),
            ("open argon valve",),
        ),
        _unrecoverable(
            "b10_contaminated_stock",
            "plate the E. coli transformation",
            "The cell stock grew mold overnight; no backup glycerol is on-site.",
            ("streak cells on agar",),
        ),
    ]
