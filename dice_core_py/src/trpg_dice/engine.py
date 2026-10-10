from __future__ import annotations

from .models import MessageContext, RollRequest, RollResponse
from .profiles import IdentityServices
from .roller import DiceRoller


class DiceEngine:
    """Application-facing facade; it returns data and never sends a message."""

    def __init__(self, identities: IdentityServices, roller: DiceRoller | None = None) -> None:
        self.identities = identities
        self.roller = roller or DiceRoller()

    def roll(self, request: RollRequest) -> RollResponse:
        card = self.identities.characters.resolve(request.context)
        display_name = self.identities.nicknames.resolve(request.context)
        expression = request.expression
        if not expression and card is not None:
            expression = str(card.attributes.get("__DefaultDice", ""))
        if not expression:
            expression = str(
                self.identities.settings.get(request.context.actor, "default_dice", "")
            )
        result = self.roller.roll(expression)
        return RollResponse(
            request=request,
            display_name=display_name,
            card_id=card.card_id if card else None,
            card_name=card.name if card else None,
            result=result,
        )
