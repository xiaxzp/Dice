from __future__ import annotations

import argparse
import json
import sys

from .commands import CommandRouter
from .engine import DiceEngine
from .models import ActorRef, MessageContext, MessageSource
from .profiles import IdentityServices, ProfileRepository
from .randomness import SeededRandomSource
from .roller import DiceRoller


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Platform-independent TRPG command router")
    parser.add_argument("command", help="dot command, for example '.r 2d6+3'")
    parser.add_argument("--platform", default="cli")
    parser.add_argument("--user-id", default="local-user")
    parser.add_argument("--source-kind", default="private")
    parser.add_argument("--source-id", default="local-source")
    parser.add_argument("--channel-id")
    parser.add_argument("--nickname", default="本地用户")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    actor = ActorRef(args.platform, args.user_id)
    source = MessageSource(
        args.platform,
        args.source_kind,
        args.source_id,
        args.channel_id,
    )
    context = MessageContext(actor, source, account_nickname=args.nickname)
    identities = IdentityServices(ProfileRepository(args.data_dir))
    roller = DiceRoller(SeededRandomSource(args.seed)) if args.seed is not None else DiceRoller()
    response = CommandRouter(DiceEngine(identities, roller)).execute(context, args.command)
    if args.as_json:
        print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(response.rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
