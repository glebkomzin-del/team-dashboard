"""Owner-scoped durable conversation access over the narrow journal gateway."""
from uuid import UUID

from memory import ValidationError


class ConversationNotFound(LookupError):
    pass


def _uuid(value, label):
    if not isinstance(value, str):
        raise ValidationError('Invalid '+label)
    try:return str(UUID(value))
    except (ValueError,AttributeError):raise ValidationError('Invalid '+label) from None


class ConversationService:
    def __init__(self, journal):
        if not hasattr(journal.store, 'call'):
            raise ValueError('Conversations require the scoped journal gateway')
        self.journal=journal

    def _owner(self, identity):
        space=self.journal.store.space();self.journal.authorize(identity,space)
        return space

    def create(self, identity, raw):
        if not isinstance(raw,dict) or set(raw)-{'conversation_id','title'} or 'conversation_id' not in raw:
            raise ValidationError('Invalid conversation request')
        identifier=_uuid(raw['conversation_id'],'conversation identity')
        title=raw.get('title')
        if title is not None and (not isinstance(title,str) or not 1<=len(title.strip())<=200):
            raise ValidationError('Invalid conversation title')
        self._owner(identity)
        result=self.journal.store.call('conversation_create',conversation_id=identifier,
            actor_id=identity['id'],title=title.strip() if title else None)
        if not isinstance(result,dict) or result.get('conversation_id')!=identifier:
            raise ValidationError('Invalid conversation receipt')
        repeated=bool(result.pop('repeated',False))
        return {'conversation':result,'repeated':repeated}

    def list(self, identity):
        self._owner(identity)
        result=self.journal.store.call('conversations_list',actor_id=identity['id'])
        if not isinstance(result,dict) or not isinstance(result.get('conversations'),list):
            raise ValidationError('Invalid conversation list')
        return result

    def get(self, identity, conversation_id, *, before_question_id=None):
        self._owner(identity);identifier=_uuid(conversation_id,'conversation identity')
        before=_uuid(before_question_id,'question identity') if before_question_id else None
        result=self.journal.store.call('conversation_get',conversation_id=identifier,
            actor_id=identity['id'],before_question_id=before)
        if result is None:raise ConversationNotFound(identifier)
        if not isinstance(result,dict) or not isinstance(result.get('conversation'),dict) \
          or result['conversation'].get('conversation_id')!=identifier or not isinstance(result.get('messages'),list):
            raise ValidationError('Invalid conversation')
        return result

    def context(self, identity, conversation_id, question_id):
        """Return bounded prior turns; generated text is reference context, never evidence."""
        result=self.get(identity,conversation_id,before_question_id=question_id)
        kept=[];size=0
        for message in reversed(result['messages']):
            if not isinstance(message,dict) or message.get('role') not in ('user','assistant') \
              or not isinstance(message.get('content'),str) or not message['content'].strip():continue
            body=message['content'];encoded=len(body.encode())
            if len(kept)>=24 or size+encoded>24000:break
            kept.append({'role':message['role'],'content':body});size+=encoded
        kept.reverse()
        return kept,max(0,len(result['messages'])-len(kept))


__all__=['ConversationService','ConversationNotFound']
