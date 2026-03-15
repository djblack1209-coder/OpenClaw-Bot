from src.shared_memory import SharedMemory


def test_workflow_feedback_stats_and_summary(tmp_path):
    memory = SharedMemory(str(tmp_path / "shared_memory.db"))

    memory.save_service_workflow_feedback(
        workflow_id="wf_1",
        original_text="帮我做一个部署方案",
        selected_option="极速落地版",
        stage1_score=3,
        stage2_score=2,
        stage3_score=1,
        improvement_focus="下次优先优化：任务交付。",
        chat_id=1001,
    )
    memory.save_service_workflow_feedback(
        workflow_id="wf_2",
        original_text="帮我优化群聊流程",
        selected_option="专家深挖版",
        stage1_score=2,
        stage2_score=3,
        stage3_score=2,
        improvement_focus="下次优先优化：客服接待、任务交付。",
        chat_id=1001,
    )

    stats = memory.get_service_workflow_feedback_stats(chat_id=1001)
    summary = memory.get_service_workflow_feedback_summary(chat_id=1001)

    assert stats["count"] == 2
    assert stats["avg_stage1"] == 2.5
    assert stats["avg_stage2"] == 2.5
    assert stats["avg_stage3"] == 1.5
    assert stats["weakest_stage"] == "任务交付"
    assert "任务交付 1.5/3" in summary
    assert "当前最弱环节：任务交付" in summary
