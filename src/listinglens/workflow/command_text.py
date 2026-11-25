from __future__ import annotations

from typing import Final

# What listinglens-memo prints (D74): its exit codes and every fixed line. A failure line is fixed
# words with fixed slots (a tool, an option, a field, a class name, rule names, a cap or a reason
# word), never a value, a word of a draft, filing metadata, the key or the contact. The memo
# itself is printed only on success.
EXIT_OK: Final = 0
EXIT_CRASH: Final = 1
EXIT_ARGUMENT: Final = 2
EXIT_CONFIG: Final = 3
EXIT_TOOLS: Final = 4
EXIT_NO_KEY: Final = 5
EXIT_MODEL: Final = 6
EXIT_FOLDER: Final = 7

PROGRAM: Final = "listinglens-memo"
DESCRIPTION: Final = "Write a cited risk memo for one company."

BAD_OPTION: Final = "listinglens-memo: --{option} is not a value the tools accept."
ONE_COMPANY: Final = "listinglens-memo: give exactly one of --cik, --ticker or --name."
BAD_ARGUMENTS: Final = "listinglens-memo: the arguments could not be read. See --help."

_WHERE: Final = " Set it in the environment or in .env in this folder."
NO_CONTACT: Final = (
    "listinglens-memo cannot start: SEC_EDGAR_CONTACT is not set to a real email address." + _WHERE
)
NO_CACHE: Final = (
    "listinglens-memo cannot start: LISTINGLENS_CACHE_DIR must be set to an absolute path." + _WHERE
)
BAD_CACHE: Final = "listinglens-memo cannot start: LISTINGLENS_CACHE_DIR is not a usable directory."
NO_KEY: Final = "listinglens-memo cannot start: LISTINGLENS_ANTHROPIC_API_KEY is not set."
BAD_OUT: Final = "listinglens-memo cannot start: the output folder cannot be written."

TOOL_ERROR: Final = "No memo: the tool {tool} returned an error."
TOOL_REFUSED: Final = "No memo: the result of {tool} was refused ({field}: {detail})."
SERVER_STOPPED: Final = "No memo: the ListingLens server stopped before the tools answered."
NO_FACTS: Final = "No memo: the tools' results could not be made into facts ({name})."

BUDGET_STOP: Final = "No memo: the run's {cap} cap stopped a call before it was sent."
WRITER_FAILED: Final = "No memo: the writer's answer was {words}."
REJECTED: Final = "No memo: the draft failed the checker twice ({rules})."
MODEL_FAILED: Final = "No memo: the model call failed ({name})."

FOLDER_EXISTS: Final = "No memo saved: the memo's folder already exists."
FOLDER_UNWRITABLE: Final = "No memo saved: the memo's folder could not be written."
CRASH: Final = "listinglens-memo stopped on an unexpected error ({name}). Nothing was saved."

COST: Final = (
    "Cost: {dollars} dollars, {tokens} tokens, price table version {version}. "
    "Model calls made: {attempts}."
)
SAVED: Final = "Saved in {folder}"

# The writer's fixed failure reasons and the Meter's caps, each as the words the console shows.
WRITER_WORDS: Final = {
    "refused": "refused by the model",
    "truncated": "cut off at the output limit",
    "context_full": "over the model's context limit",
    "empty": "empty",
}
CAP_WORDS: Final = {"attempts": "attempt", "tokens": "token", "dollars": "dollar"}

# The trace's line (D76), printed after the run's last line: the id of a sent trace (on stdout
# after "Saved in" on success, on stderr after the exit and cost lines on a failure), or why it
# was not sent (always on stderr). A detail is an HTTP status code or an exception's class name.
TRACE_SENT: Final = "Trace sent to Langfuse: {trace_id}"
TRACE_NOT_SENT: Final = "Trace not sent: {reason}."
TRACE_REASONS: Final = {
    "host": "LISTINGLENS_LANGFUSE_HOST is not one of Langfuse's cloud hosts",
    "keys": (
        "only one of LISTINGLENS_LANGFUSE_PUBLIC_KEY and LISTINGLENS_LANGFUSE_SECRET_KEY is set"
    ),
    "timeout": "Langfuse did not answer in time",
    "connection": "the connection to Langfuse failed",
    "status": "Langfuse answered HTTP {detail}",
    "too_large": "the trace is larger than Langfuse accepts",
    "unexpected": "an unexpected error ({detail})",
}
