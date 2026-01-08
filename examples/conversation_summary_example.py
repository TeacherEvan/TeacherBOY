"""
Example: Conversation Summarization Integration

This example demonstrates how to integrate the conversation summarization
service into the LLM agent workflow for automatic token optimization.
"""

import asyncio
from datetime import datetime
from typing import List, Dict, Optional

# Mock imports (replace with actual imports in production)
class MockGitHubModelsService:
    """Mock GitHub Models service for example."""
    async def chat_completion(self, messages, model, temperature, max_tokens):
        return """## Summary
The user asked about Zeus's capabilities and received an overview of the translation, news, and calendar features. The conversation covered setup instructions and usage examples.

## Key Topics
- Zeus bot capabilities
- Translation features
- News agent functionality
- Calendar and reminders

## Important Context
User is new to Zeus and learning the basic features.

## Pending Actions
None - user is still exploring features."""


async def example_conversation_summarization():
    """
    Example workflow showing conversation summarization in action.
    """
    from src.services.conversation_summarization_service import (
        conversation_summarization_service,
    )
    
    # Set up LLM service (in production, use actual service)
    mock_llm = MockGitHubModelsService()
    conversation_summarization_service.set_llm_service(mock_llm)
    
    # Simulate a long conversation
    conversation_messages = [
        {"role": "user", "content": "What can Zeus do?", "timestamp": "2025-01-09T10:00:00"},
        {"role": "assistant", "content": "Zeus is a multi-agent LINE bot with translation, news, calendar, and AI chat features.", "timestamp": "2025-01-09T10:00:05"},
        {"role": "user", "content": "How do I use translation?", "timestamp": "2025-01-09T10:01:00"},
        {"role": "assistant", "content": "Just send Thai or English text - Zeus auto-translates!", "timestamp": "2025-01-09T10:01:05"},
        # ... many more messages ...
    ] * 20  # Simulate 80 messages
    
    print(f"Original conversation: {len(conversation_messages)} messages")
    
    # Check if summarization is needed
    should_summarize = await conversation_summarization_service.should_summarize(
        messages=conversation_messages,
        token_threshold=50000,
        message_threshold=50,
    )
    
    print(f"Should summarize: {should_summarize}")
    
    if should_summarize:
        # Summarize the conversation
        print("\nSummarizing conversation...")
        
        summary = await conversation_summarization_service.summarize_conversation(
            messages=conversation_messages,
            preserve_recent=5,  # Keep last 5 messages unsummarized
            model="openai/gpt-4o-mini",
        )
        
        if summary:
            print(f"\n✅ Summarization Complete!")
            print(f"   Original: {summary.original_message_count} messages, {summary.original_token_count} tokens")
            print(f"   Compressed: ~{summary.compressed_token_count} tokens")
            print(f"   Compression ratio: {summary.compression_ratio*100:.1f}%")
            print(f"   Tokens saved: {summary.original_token_count - summary.compressed_token_count}")
            
            print(f"\n📋 Key Topics:")
            for topic in summary.covered_topics:
                print(f"   - {topic}")
            
            print(f"\n📝 Summary Preview:")
            print(summary.summary_text[:300] + "...")
            
            # Create compressed history
            recent_messages = conversation_messages[-5:]
            compressed_history = conversation_summarization_service.create_compressed_history(
                summary=summary,
                recent_messages=recent_messages,
            )
            
            print(f"\n📊 Compressed History:")
            print(f"   Total messages: {len(compressed_history)}")
            print(f"   Summary message + {len(recent_messages)} recent messages")
            
            # Show the compressed history structure
            print(f"\n🔍 Compressed History Structure:")
            for i, msg in enumerate(compressed_history, 1):
                role = msg.get("role", "unknown")
                content_preview = msg.get("content", "")[:100] + "..."
                is_summary = msg.get("metadata", {}).get("is_summary", False)
                marker = "[SUMMARY]" if is_summary else ""
                print(f"   {i}. {role.title()} {marker}: {content_preview}")


async def example_integration_with_llm_agent():
    """
    Example showing how to integrate summarization with LLM agent.
    """
    print("\n" + "="*80)
    print("Example: Integration with LLM Agent")
    print("="*80 + "\n")
    
    from src.services.conversation_summarization_service import (
        conversation_summarization_service,
    )
    from src.services.prompt_builder_service import (
        prompt_builder_service,
        ContextBlock,
    )
    
    # Simulate conversation history (in production, get from ConversationMemoryService)
    conversation_messages = [
        {"role": "user", "content": "Hello Zeus!"},
        {"role": "assistant", "content": "Greetings! How may I assist you?"},
        # ... many more messages ...
    ] * 30  # 60 messages total
    
    print(f"Current conversation: {len(conversation_messages)} messages")
    
    # Check if we should summarize
    if await conversation_summarization_service.should_summarize(
        messages=conversation_messages,
        message_threshold=50,
    ):
        print("⚠️  Conversation exceeds threshold - summarizing...")
        
        # Summarize (mock for example)
        # In production, this would actually call the LLM
        mock_llm = MockGitHubModelsService()
        conversation_summarization_service.set_llm_service(mock_llm)
        
        summary = await conversation_summarization_service.summarize_conversation(
            messages=conversation_messages,
            preserve_recent=5,
        )
        
        if summary:
            # Create compressed history
            compressed = conversation_summarization_service.create_compressed_history(
                summary=summary,
                recent_messages=conversation_messages[-5:],
            )
            
            # Use compressed history in prompt
            conversation_context = prompt_builder_service.create_conversation_context(
                messages=compressed,
                max_messages=10,  # Will use all compressed messages
                priority=2,
            )
            
            print(f"\n✅ Using compressed conversation context:")
            print(f"   Messages: {len(compressed)} (down from {len(conversation_messages)})")
            print(f"   Estimated tokens: {conversation_context.estimated_tokens}")
            print(f"   Token savings: {summary.original_token_count - summary.compressed_token_count}")
    
    print("\n✅ Integration example complete!")


async def main():
    """Run all examples."""
    print("🚀 Conversation Summarization Examples\n")
    
    # Example 1: Basic summarization
    await example_conversation_summarization()
    
    # Example 2: Integration with LLM agent
    await example_integration_with_llm_agent()
    
    print("\n" + "="*80)
    print("All examples completed successfully!")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
