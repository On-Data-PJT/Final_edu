(() => {
  "use strict";

  const state = {
    page1: {
      courses: [],
      selectedCourseId: "",
      selectedCourse: null,
      preview: null,
      previewFile: null,
      blocks: [],
    },
    page2: {
      result: null,
      mode: "combined",
      instructorIndex: 0,
      instructorName: "",
      charts: new Map(),
    },
    page3: {
      result: null,
    },
  };

  const CSS = {
    hidden: "is-hidden",
    open: "is-open",
    active: "is-active",
    disabled: "is-disabled",
    selected: "is-selected",
  };

  const SELECTORS = {
    page1CoursesData: "#page1-courses-data",
    courseModal: "#course-modal, [data-testid='course-modal']",
    courseListPanel: "#course-list-panel, [data-testid='course-list-panel']",
    courseModalForm: "#course-modal-form, [data-testid='course-modal-form']",
    coursePreviewState: "#course-preview-state, [data-testid='course-preview-state']",
    coursePreviewTable: "#course-preview-table, [data-testid='course-preview-table']",
    courseSaveButton: "#course-save-button, [data-testid='course-save-button']",
    selectedCourseId: "#selected-course-id, [data-testid='selected-course-id']",
    selectedCourseName: "#selected-course-name, [data-testid='selected-course-name']",
    page1Workspace: "#page1-workspace, [data-testid='page1-workspace']",
    instructorBlocks: "#instructor-blocks, [data-testid='instructor-blocks']",
    instructorBlockTemplate: "#instructor-block-template, [data-testid='instructor-block-template']",
    addInstructorBlock: "#add-instructor-block, [data-testid='add-instructor-block']",
    submitAnalysis: "#submit-analysis, [data-testid='submit-analysis']",
    analysisForm: "form[action='/analyze'], [data-testid='analysis-form']",
    courseForm: "#course-modal-form, [data-testid='course-modal-form']",
    openCourseModal: [
      "[data-open-course-modal]",
      "[data-testid='open-course-modal']",
      "[aria-controls='course-modal']",
      "#open-course-modal",
    ],
    openCourseList: [
      "[data-open-course-list]",
      "[data-testid='open-course-list']",
      "[aria-controls='course-list-panel']",
      "#open-course-list",
    ],
    closeDialogs: [
      "[data-close-dialog]",
      "[data-testid='close-dialog']",
      "[data-close='course-modal']",
      "[data-close='course-list-panel']",
    ],
    page2ResultData: "#page2-result-data, [data-testid='page2-result-data']",
    page2ModeButtons: [
      "[data-view-mode]",
      "[data-mode-toggle]",
      "[data-page2-mode]",
    ],
    page2InstructorButtons: [
      "[data-instructor-index]",
      "[data-instructor-name]",
      "[data-page2-instructor]",
    ],
    page2RoseChart: "#page2-rose-chart, [data-chart='rose']",
    page2WordCloud: "#page2-wordcloud-chart, [data-chart='wordcloud']",
    page2AverageBar: "#page2-average-bar-chart, [data-chart='average-bar']",
    page2InstructorBar: "#page2-instructor-bar-chart, [data-chart='instructor-bar']",
    page2LineChart: "#page2-line-chart, [data-chart='line']",
    page2SelectedInstructor: "#page2-selected-instructor, [data-testid='page2-selected-instructor'], [data-page2-selected-instructor]",
    page2InstructorNav: "[data-instructor-nav]",
    page3ResultData: "#page3-result-data, [data-testid='page3-result-data']",
    page3InsightContainer: "#page3-insights, [data-page3-insights], [data-testid='page3-insights']",
    page3TrendStatus: "#page3-trend-status, [data-page3-trend-status], [data-testid='page3-trend-status']",
  };

  const CHART_COLORS = ["#5b6cff", "#7a6ff0", "#63b68b", "#f2c66d", "#8fc9ff", "#ff8a7a", "#6bc1c7", "#b4a0ff"];

  function init() {
    initPage1();
    initPage2();
    initPage3();
    window.FinalEduUI = { state };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }

  function initPage1() {
    const coursesScript = $(SELECTORS.page1CoursesData);
    const courses = safeParseJSON(text(coursesScript), []);
    if (Array.isArray(courses)) {
      state.page1.courses = courses;
    }

    const courseModal = $(SELECTORS.courseModal);
    const courseListPanel = $(SELECTORS.courseListPanel);
    const courseForm = $(SELECTORS.courseForm);
    const analysisForm = $(SELECTORS.analysisForm);
    const workspace = $(SELECTORS.page1Workspace);
    const blocksRoot = $(SELECTORS.instructorBlocks);
    const template = $(SELECTORS.instructorBlockTemplate);
    const addBlockButton = $(SELECTORS.addInstructorBlock);
    const submitButton = $(SELECTORS.submitAnalysis);
    const saveButton = $(SELECTORS.courseSaveButton);
    const previewState = $(SELECTORS.coursePreviewState);
    const previewTable = $(SELECTORS.coursePreviewTable);
    const selectedCourseId = ensureHiddenInput(analysisForm, "course_id");
    const selectedCourseName = ensureHiddenInput(analysisForm, "course_name");
    const manifestInput = ensureHiddenInput(analysisForm, "instructor_manifest");
    const courseFileInput = findFirst(courseForm, [
      "input[type='file'][name='curriculum_pdf']",
      "[data-role='course-curriculum-file']",
      "[data-testid='course-curriculum-file']",
    ]);
    const courseNameInput = findFirst(courseForm, [
      "input[name='course_name']",
      "[data-role='course-name']",
      "[data-testid='course-name']",
    ]);

    if (workspace) {
      workspace.dataset.state = "disabled";
    }

    if (courseForm && courseFileInput) {
      courseFileInput.addEventListener("change", () => {
        if (courseFileInput.files && courseFileInput.files.length > 0) {
          previewCourse(courseForm, courseFileInput, courseNameInput, previewState, previewTable, saveButton);
        }
      });
    }

    if (courseForm) {
      courseForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!state.page1.preview) {
          await previewCourse(courseForm, courseFileInput, courseNameInput, previewState, previewTable, saveButton);
          return;
        }
        await saveCourse(courseForm, courseFileInput, courseNameInput, previewState, previewTable, saveButton, courseModal);
      });
    }

    bindDialog(courseModal, SELECTORS.openCourseModal, SELECTORS.closeDialogs, () => {
      if (courseNameInput && !courseNameInput.value && state.page1.selectedCourse) {
        courseNameInput.value = state.page1.selectedCourse.name;
      }
      if (courseFileInput && courseFileInput.files && courseFileInput.files.length > 0 && !state.page1.preview) {
        previewCourse(courseForm, courseFileInput, courseNameInput, previewState, previewTable, saveButton);
      }
    });

    bindPanel(courseListPanel, SELECTORS.openCourseList, SELECTORS.closeDialogs);

    if (addBlockButton) {
      addBlockButton.addEventListener("click", (event) => {
        event.preventDefault();
        if (!state.page1.selectedCourseId) {
          return;
        }
        addInstructorBlock(blocksRoot, template, analysisForm, manifestInput);
        syncPage1State(workspace, selectedCourseId, selectedCourseName, submitButton, manifestInput);
      });
    }

    if (submitButton && analysisForm) {
      submitButton.addEventListener("click", (event) => {
        event.preventDefault();
        if (!canSubmitAnalysis()) {
          setStatus(previewState, "과정 선택, 강사 2명 이상, 각 강사 자료 등록이 필요합니다.");
          return;
        }
        analysisForm.requestSubmit ? analysisForm.requestSubmit(submitButton) : analysisForm.submit();
      });
    }

    if (workspace) {
      workspace.addEventListener("click", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) {
          return;
        }
        const action = target.closest("[data-action]");
        if (!action) {
          return;
        }
        const block = action.closest("[data-instructor-block]");
        if (!block) {
          return;
        }
        const actionName = action.getAttribute("data-action");
        if (actionName === "toggle-files") {
          toggleBlockPanel(block, "files");
        }
        if (actionName === "toggle-youtube") {
          toggleBlockPanel(block, "youtube");
        }
      });

      workspace.addEventListener("input", () => {
        syncPage1State(workspace, selectedCourseId, selectedCourseName, submitButton, manifestInput);
      });

      workspace.addEventListener("change", () => {
        syncPage1State(workspace, selectedCourseId, selectedCourseName, submitButton, manifestInput);
      });
    }

    if (courseListPanel) {
      courseListPanel.addEventListener("click", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) {
          return;
        }
        const button = target.closest("[data-course-select]");
        if (!button) {
          return;
        }
        const courseId = button.getAttribute("data-course-select");
        const course = state.page1.courses.find((item) => item.id === courseId);
        if (course) {
          selectCourse(course, {
            workspace,
            selectedCourseId,
            selectedCourseName,
            submitButton,
            manifestInput,
            courseListPanel,
          });
        }
      });
    }

    qsa("[data-course-card]").forEach((button) => {
      button.addEventListener("click", () => {
        const courseId = button.getAttribute("data-course-select") || button.getAttribute("data-course-id");
        const course = state.page1.courses.find((item) => item.id === courseId);
        if (course) {
          selectCourse(course, {
            workspace,
            selectedCourseId,
            selectedCourseName,
            submitButton,
            manifestInput,
            courseListPanel,
          });
        }
      });
    });

    if (!state.page1.courses.length) {
      fetchCourses().then((items) => {
        if (items.length) {
          state.page1.courses = items;
          renderCourseList(courseListPanel);
        }
      });
    } else {
      renderCourseList(courseListPanel);
    }

    if (blocksRoot) {
      const existingBlocks = qsa("[data-instructor-block]", blocksRoot);
      if (!existingBlocks.length) {
        addInstructorBlock(blocksRoot, template, analysisForm, manifestInput);
      } else {
        state.page1.blocks = existingBlocks.slice();
        existingBlocks.forEach((block, index) => bindInstructorBlock(block, index + 1));
      }
    }

    syncPage1State(workspace, selectedCourseId, selectedCourseName, submitButton, manifestInput);
    updateCourseListSelection(courseListPanel);
  }

  function initPage2() {
    const dataScript = $(SELECTORS.page2ResultData);
    const result = safeParseJSON(text(dataScript), null);
    if (!result || typeof result !== "object") {
      return;
    }
    state.page2.result = result;

    const containers = {
      rose: $(SELECTORS.page2RoseChart),
      wordcloud: $(SELECTORS.page2WordCloud),
      averageBar: $(SELECTORS.page2AverageBar),
      instructorBar: $(SELECTORS.page2InstructorBar),
      line: $(SELECTORS.page2LineChart),
      selectedInstructorTargets: qsa(SELECTORS.page2SelectedInstructor),
    };
    const modeButtons = qsa(joinSelectors(SELECTORS.page2ModeButtons));
    const instructorButtons = qsa(joinSelectors(SELECTORS.page2InstructorButtons));

    if (!result.instructors || !result.instructors.length) {
      return;
    }

    state.page2.instructorIndex = resolveInstructorIndex(
      result.selected_instructor || result.selectedInstructor || result.instructors[0].name,
      0,
    );
    state.page2.instructorName = result.instructors[state.page2.instructorIndex]?.name || result.selected_instructor || result.selectedInstructor || result.instructors[0].name;

    modeButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const mode = button.getAttribute("data-view-mode") || button.getAttribute("data-mode-toggle") || button.getAttribute("data-page2-mode");
        if (!mode) {
          return;
        }
        state.page2.mode = normalizeMode(mode);
        syncModeButtons(modeButtons);
        updatePage2Charts(containers, { updateRoseWordcloud: false });
      });
    });
    syncModeButtons(modeButtons);

    instructorButtons.forEach((button, index) => {
      const instructorIndex = resolveInstructorIndex(button.getAttribute("data-instructor-index"), index);
      button.addEventListener("click", () => {
        selectPage2Instructor(
          button.getAttribute("data-instructor-index") ?? instructorIndex,
          containers,
          { updateRoseWordcloud: true, updateModeCharts: false, updateLine: true },
        );
      });
    });
    syncInstructorButtons(instructorButtons, state.page2.instructorIndex, state.page2.instructorName);

    document.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      const nav = target.closest(SELECTORS.page2InstructorNav);
      if (!nav || !state.page2.result) {
        return;
      }
      const direction = nav.getAttribute("data-instructor-nav");
      if (direction !== "prev" && direction !== "next") {
        return;
      }
      event.preventDefault();
      selectPage2Instructor(
        direction === "prev" ? state.page2.instructorIndex - 1 : state.page2.instructorIndex + 1,
        containers,
        { updateRoseWordcloud: true, updateModeCharts: false, updateLine: true },
      );
    });

    updatePage2Charts(containers);
    window.addEventListener("resize", debounce(() => resizeCharts(), 100));
  }

  function initPage3() {
    const dataScript = $(SELECTORS.page3ResultData);
    const result = safeParseJSON(text(dataScript), null);
    if (!result || typeof result !== "object") {
      return;
    }
    state.page3.result = result;
    const root = $(SELECTORS.page3InsightContainer);
    if (root && !root.children.length) {
      renderInsights(root, result);
    }
    const trendStatus = $(SELECTORS.page3TrendStatus);
    if (trendStatus) {
      const trendMeta = trendStatusMeta(result.external_trends_status);
      trendStatus.textContent = trendMeta.message;
      trendStatus.classList.remove("is-planned", "is-success", "is-failed", "is-unknown");
      trendStatus.classList.add(trendMeta.className);
    }
  }

  function previewCourse(courseForm, courseFileInput, courseNameInput, previewState, previewTable, saveButton) {
    if (!courseForm || !courseFileInput || !courseFileInput.files || !courseFileInput.files.length) {
      setStatus(previewState, "PDF 파일을 선택해 주세요.");
      return Promise.resolve(null);
    }
    const file = courseFileInput.files[0];
    if (!file) {
      setStatus(previewState, "PDF 파일을 선택해 주세요.");
      return Promise.resolve(null);
    }

    const fd = new FormData();
    fd.append("curriculum_pdf", file, file.name);
    state.page1.previewFile = file;
    setBusy(saveButton, true, "미리보는 중");
    setStatus(previewState, "커리큘럼 PDF를 분석하는 중입니다.");

    return fetchJson("/courses/preview", {
      method: "POST",
      body: fd,
    })
      .then((payload) => {
        state.page1.preview = normalizePreview(payload);
        renderCoursePreview(previewTable, previewState, state.page1.preview, courseNameInput?.value || "");
        setButtonDisabled(saveButton, false);
        setBusy(saveButton, false);
        return state.page1.preview;
      })
      .catch((error) => {
        setStatus(previewState, `미리보기에 실패했습니다. ${error.message}`);
        setButtonDisabled(saveButton, true);
        setBusy(saveButton, false);
        return null;
      });
  }

  function saveCourse(courseForm, courseFileInput, courseNameInput, previewState, previewTable, saveButton, courseModal) {
    if (!state.page1.preview || !courseFileInput?.files?.length) {
      setStatus(previewState, "먼저 PDF를 미리보기로 분석해 주세요.");
      return Promise.resolve(null);
    }

    const fd = new FormData();
    fd.append("course_name", courseNameInput?.value?.trim() || "이름 없는 과정");
    fd.append("raw_curriculum_text", state.page1.preview.raw_curriculum_text || "");
    fd.append("sections_json", JSON.stringify(readPreviewSections(previewTable)));
    fd.append("curriculum_pdf", courseFileInput.files[0], courseFileInput.files[0].name);
    setBusy(saveButton, true, "저장 중");

    return fetchJson("/courses", {
      method: "POST",
      body: fd,
    })
      .then((payload) => {
        state.page1.courses = Array.isArray(payload.courses) ? payload.courses : state.page1.courses;
        if (payload.course) {
          selectCourse(payload.course, {
            workspace: $(SELECTORS.page1Workspace),
            selectedCourseId: $(SELECTORS.selectedCourseId),
            selectedCourseName: $(SELECTORS.selectedCourseName),
            submitButton: $(SELECTORS.submitAnalysis),
            manifestInput: ensureHiddenInput($(SELECTORS.analysisForm), "instructor_manifest"),
            courseListPanel: $(SELECTORS.courseListPanel),
          });
        }
        renderCourseList($(SELECTORS.courseListPanel));
        setStatus(previewState, "과정이 저장되었습니다.");
        if (courseModal) {
          closeSurface(courseModal);
        }
        setBusy(saveButton, false);
        return payload;
      })
      .catch((error) => {
        setStatus(previewState, `저장에 실패했습니다. ${error.message}`);
        setBusy(saveButton, false);
        return null;
      });
  }

  function renderCoursePreview(previewTable, previewState, preview, courseName) {
    if (!previewTable) {
      return;
    }
    previewTable.innerHTML = "";
    const table = document.createElement("table");
    table.className = "course-preview-table";
    const thead = document.createElement("thead");
    thead.innerHTML = `
      <tr>
        <th>#</th>
        <th>대주제</th>
        <th>설명</th>
        <th>목표 비중</th>
      </tr>
    `;
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    preview.sections.forEach((section, index) => {
      const row = document.createElement("tr");
      row.dataset.sectionId = section.id;
      row.dataset.coursePreviewRow = "true";
      row.innerHTML = `
        <td>${index + 1}</td>
        <td><input type="text" data-section-field="title" value="${escapeAttr(section.title)}"></td>
        <td><input type="text" data-section-field="description" value="${escapeAttr(section.description)}"></td>
        <td><input type="number" min="0" step="0.1" max="100" data-section-field="target_weight" value="${escapeAttr(String(section.target_weight ?? 0))}"></td>
      `;
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    previewTable.appendChild(table);

    const footer = document.createElement("div");
    footer.className = "course-preview-meta";
    footer.dataset.coursePreviewMeta = "true";
    footer.textContent = `${courseName ? `${courseName} · ` : ""}${preview.sections.length}개 대주제 · ${summaryPreviewWeights(preview.sections)}`;
    previewTable.appendChild(footer);

    if (previewState) {
      const warnings = preview.warnings && preview.warnings.length ? ` 경고 ${preview.warnings.length}건.` : "";
      previewState.textContent = `초안 추출 완료.${warnings}`;
    }

    qsa("input[data-section-field]", previewTable).forEach((input) => {
      input.addEventListener("input", () => {
        if (previewState) {
          previewState.textContent = `초안 수정 중 · 합계 ${summaryPreviewWeights(readPreviewSections(previewTable))}`;
        }
      });
    });
  }

  function readPreviewSections(previewTable) {
    if (!previewTable) {
      return [];
    }
    return qsa("[data-course-preview-row]", previewTable).map((row) => {
      const title = findOne(row, ["[data-section-field='title']", "input[data-section-field='title']"]);
      const description = findOne(row, ["[data-section-field='description']", "input[data-section-field='description']"]);
      const weight = findOne(row, ["[data-section-field='target_weight']", "input[data-section-field='target_weight']"]);
      return {
        id: row.dataset.sectionId || uniqueId("section"),
        title: title ? title.value.trim() : "",
        description: description ? description.value.trim() : "",
        target_weight: weight ? Number(weight.value || 0) : 0,
      };
    }).filter((section) => section.title);
  }

  function renderCourseList(courseListPanel) {
    if (!courseListPanel) {
      return;
    }
    const target = ensureRenderedContainer(courseListPanel, "course-list-items", "div");
    target.innerHTML = "";
    if (!state.page1.courses.length) {
      const empty = document.createElement("p");
      empty.className = "course-list-empty";
      empty.textContent = "추가된 과정이 없습니다.";
      target.appendChild(empty);
      return;
    }

    state.page1.courses.forEach((course) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "course-list-item";
      card.dataset.courseSelect = course.id;
      card.dataset.courseItem = "true";
      if (course.id === state.page1.selectedCourseId) {
        card.classList.add(CSS.selected);
      }
      card.innerHTML = `
        <div class="course-list-item-head">
          <strong>${escapeHtml(course.name)}</strong>
          <span class="course-state-chip is-sage">목표 비중 추출 완료</span>
        </div>
        <span>${course.sections.length}개 대주제</span>
        <small>목표 비중 합계 ${formatCourseWeightTotal(course.sections)}%</small>
      `;
      target.appendChild(card);
    });
  }

  function updateCourseListSelection(courseListPanel) {
    qsa("[data-course-card]").forEach((button) => {
      const active = (button.getAttribute("data-course-select") || button.getAttribute("data-course-id")) === state.page1.selectedCourseId;
      button.classList.toggle(CSS.selected, active);
      button.classList.toggle(CSS.active, active);
    });
    if (!courseListPanel) {
      return;
    }
    qsa("[data-course-item]", courseListPanel).forEach((button) => {
      const active = button.getAttribute("data-course-select") === state.page1.selectedCourseId;
      button.classList.toggle(CSS.selected, active);
      button.classList.toggle(CSS.active, active);
    });
  }

  function formatCourseWeightTotal(sections) {
    const total = (Array.isArray(sections) ? sections : []).reduce((sum, section) => sum + Number(section?.target_weight || 0), 0);
    return total.toFixed(1);
  }

  function selectCourse(course, refs) {
    state.page1.selectedCourse = course;
    state.page1.selectedCourseId = course.id;
    const { workspace, selectedCourseId, selectedCourseName, submitButton, manifestInput, courseListPanel } = refs;

    setFieldValue(selectedCourseId, course.id);
    setFieldValue(selectedCourseName, course.name);
    state.page1.preview = null;
    state.page1.previewFile = null;

    if (workspace) {
      workspace.dataset.state = "active";
      workspace.classList.remove(CSS.disabled);
    }

    if (manifestInput) {
      manifestInput.value = JSON.stringify(getInstructorManifest(), null, 0);
    }

    enableWorkspaceInputs(true);
    renderCourseList(courseListPanel);
    updateCourseListSelection(courseListPanel);
    syncPage1State(workspace, selectedCourseId, selectedCourseName, submitButton, manifestInput);
  }

  function syncPage1State(workspace, selectedCourseId, selectedCourseName, submitButton, manifestInput) {
    const selectedId = state.page1.selectedCourseId || valueOf(selectedCourseId);
    const selectedCourse = state.page1.courses.find((item) => item.id === selectedId) || state.page1.selectedCourse;
    state.page1.selectedCourse = selectedCourse || null;
    state.page1.selectedCourseId = selectedCourse?.id || "";

    setFieldValue(selectedCourseId, selectedCourse?.id || "");
    setFieldValue(selectedCourseName, selectedCourse?.name || "");

    if (workspace) {
      workspace.dataset.state = selectedCourse ? "active" : "disabled";
      workspace.classList.toggle(CSS.disabled, !selectedCourse);
    }

    if (manifestInput) {
      manifestInput.value = JSON.stringify(getInstructorManifest(), null, 0);
    }

    enableWorkspaceInputs(Boolean(selectedCourse));
    if (submitButton) {
      setButtonDisabled(submitButton, !canSubmitAnalysis());
    }

    if (courseSaveButton()) {
      setButtonDisabled(courseSaveButton(), !state.page1.preview);
    }
  }

  function enableWorkspaceInputs(enabled) {
    const root = $(SELECTORS.page1Workspace);
    if (!root) {
      return;
    }
    qsa("input, textarea, button, select", root).forEach((el) => {
      el.disabled = !enabled;
    });
  }

  function addInstructorBlock(blocksRoot, template, analysisForm, manifestInput) {
    if (!blocksRoot) {
      return null;
    }
    const index = state.page1.blocks.length + 1;
    const blockId = uniqueId("instructor");
    const block = createInstructorBlock(blockId, index, template);
    blocksRoot.appendChild(block);
    state.page1.blocks.push(block);
    bindInstructorBlock(block, index);
    syncPage1State($(SELECTORS.page1Workspace), $(SELECTORS.selectedCourseId), $(SELECTORS.selectedCourseName), $(SELECTORS.submitAnalysis), manifestInput);
    if (analysisForm) {
      manifestInput.value = JSON.stringify(getInstructorManifest(), null, 0);
    }
    return block;
  }

  function createInstructorBlock(blockId, index, template) {
    if (template && template.content) {
      const fragment = template.content.cloneNode(true);
      const node = fragment.firstElementChild || fragment.firstElementChild;
      const block = node || fragment;
      if (block instanceof HTMLElement) {
        block.dataset.instructorBlock = "true";
        block.dataset.blockId = blockId;
        decorateInstructorBlock(block, blockId, index);
        return block;
      }
    }

    const block = document.createElement("article");
    block.className = "instructor-block";
    block.dataset.instructorBlock = "true";
    block.dataset.blockId = blockId;
    block.innerHTML = `
      <div class="instructor-block__header">
        <label class="field instructor-block__name">
          <span>강사명</span>
          <input type="text" data-role="instructor-name" name="instructor_name__${blockId}" placeholder="예: 김강사">
        </label>
        <span class="instructor-block__status" data-role="block-status">자료 없음</span>
      </div>
      <div class="instructor-block__actions">
        <button type="button" class="icon-chip" data-action="toggle-files">파일 업로드</button>
        <button type="button" class="icon-chip" data-action="toggle-youtube">YouTube 링크</button>
      </div>
      <div class="instructor-block__panels">
        <section class="instructor-block__panel" data-role="files-panel" hidden>
          <label class="field">
            <span>강의 자료 파일</span>
            <input type="file" multiple accept=".pdf,.pptx,.txt,.md" data-role="instructor-files" name="instructor_files__${blockId}">
          </label>
        </section>
        <section class="instructor-block__panel" data-role="youtube-panel" hidden>
          <label class="field">
            <span>YouTube URL</span>
            <textarea rows="4" data-role="instructor-youtube" name="instructor_youtube_urls__${blockId}" placeholder="한 줄에 하나씩 입력"></textarea>
          </label>
        </section>
      </div>
    `;
    decorateInstructorBlock(block, blockId, index);
    return block;
  }

  function decorateInstructorBlock(block, blockId, index) {
    block.dataset.instructorBlock = "true";
    block.dataset.blockId = blockId;
    block.dataset.blockIndex = String(index);

    const nameInput = findOne(block, [
      "[data-role='instructor-name']",
      "input[type='text']",
    ]);
    const fileInput = findOne(block, [
      "[data-role='instructor-files']",
      "input[type='file']",
    ]);
    const youtubeInput = findOne(block, [
      "[data-role='instructor-youtube']",
      "textarea",
    ]);
    const status = findOne(block, ["[data-role='block-status']"]);
    const filePanel = findOne(block, ["[data-role='files-panel']"]);
    const youtubePanel = findOne(block, ["[data-role='youtube-panel']"]);

    if (nameInput) {
      nameInput.name = `instructor_name__${blockId}`;
      nameInput.dataset.blockField = "name";
      nameInput.addEventListener("input", () => updateBlockStatus(block));
    }
    if (fileInput) {
      fileInput.name = `instructor_files__${blockId}`;
      fileInput.dataset.blockField = "files";
      fileInput.addEventListener("change", () => updateBlockStatus(block));
    }
    if (youtubeInput) {
      youtubeInput.name = `instructor_youtube_urls__${blockId}`;
      youtubeInput.dataset.blockField = "youtube";
      youtubeInput.addEventListener("input", () => updateBlockStatus(block));
    }
    if (status) {
      status.dataset.blockStatus = "true";
    }
    if (filePanel) {
      filePanel.dataset.blockPanel = "files";
    }
    if (youtubePanel) {
      youtubePanel.dataset.blockPanel = "youtube";
    }

    updateBlockStatus(block);
  }

  function bindInstructorBlock(block, index) {
    decorateInstructorBlock(block, block.dataset.blockId || uniqueId("instructor"), index);
  }

  function toggleBlockPanel(block, type) {
    const panel = findOne(block, [`[data-role='${type}-panel']`, `[data-block-panel='${type}']`]);
    if (!panel) {
      return;
    }
    const isOpen = !panel.hasAttribute("hidden");
    panel.hidden = isOpen;
    panel.classList.toggle(CSS.open, !isOpen);
  }

  function updateBlockStatus(block) {
    const nameInput = findOne(block, ["[data-role='instructor-name']"]);
    const fileInput = findOne(block, ["[data-role='instructor-files']"]);
    const youtubeInput = findOne(block, ["[data-role='instructor-youtube']"]);
    const status = findOne(block, ["[data-role='block-status']"]);

    const hasName = Boolean(nameInput && nameInput.value.trim());
    const fileCount = fileInput && fileInput.files ? fileInput.files.length : 0;
    const youtubeCount = youtubeInput ? youtubeInput.value.split(/\n+/).map((line) => line.trim()).filter(Boolean).length : 0;
    const hasAssets = fileCount > 0 || youtubeCount > 0;

    block.dataset.valid = String(hasName && hasAssets);
    if (status) {
      if (!hasName && !hasAssets) {
        status.textContent = "자료 없음";
      } else if (hasName && !hasAssets) {
        status.textContent = "자료 대기";
      } else if (!hasName && hasAssets) {
        status.textContent = "강사명 필요";
      } else {
        status.textContent = `파일 ${fileCount}개 · 링크 ${youtubeCount}개`;
      }
    }
    syncPage1State($(SELECTORS.page1Workspace), $(SELECTORS.selectedCourseId), $(SELECTORS.selectedCourseName), $(SELECTORS.submitAnalysis), ensureHiddenInput($(SELECTORS.analysisForm), "instructor_manifest"));
  }

  function getInstructorManifest() {
    return state.page1.blocks
      .filter((block) => block.dataset.blockId)
      .map((block) => ({ id: block.dataset.blockId }));
  }

  function canSubmitAnalysis() {
    if (!state.page1.selectedCourseId) {
      return false;
    }
    const validBlocks = state.page1.blocks.filter((block) => block.dataset.valid === "true");
    return validBlocks.length >= 2;
  }

  function renderPage2Charts(containers, options = {}) {
    if (!state.page2.result) {
      return;
    }
    const result = state.page2.result;
    const sections = Array.isArray(result.course?.sections) ? result.course.sections : (result.sections || []);
    const instructors = Array.isArray(result.instructors) ? result.instructors : [];
    const selected = getSelectedInstructorRecord(instructors);
    state.page2.instructorIndex = selected.index;
    state.page2.instructorName = selected.instructor ? selected.instructor.name : "";

    if (options.syncSelection !== false) {
      setTextForTargets(containers.selectedInstructorTargets, state.page2.instructorName || "미선택");
      syncInstructorButtons(qsa(joinSelectors(SELECTORS.page2InstructorButtons)), state.page2.instructorIndex, state.page2.instructorName);
      syncModeButtons(qsa(joinSelectors(SELECTORS.page2ModeButtons)));
    }

    const roseData = result.rose_series_by_instructor?.[state.page2.instructorName] || selected.instructor?.section_coverages?.map((coverage) => ({
      name: coverage.section_title,
      value: Math.round((coverage.token_share || 0) * 10000) / 100,
    })) || [];
    const wordCloudData = (result.keywords_by_instructor?.[state.page2.instructorName] || []).map((item, index) => ({
      name: item.text,
      value: item.value,
      textStyle: {
        color: stableColorForKey(item.text || String(index)),
      },
    }));
    const modeData = result.mode_series?.[state.page2.mode] || result.mode_series?.combined || {};
    const averageSeries = Array.isArray(modeData.average) ? modeData.average : [];
    const instructorSeries = modeData.instructors || {};
    const lineSeries = result.line_series_by_mode?.[state.page2.mode] || result.line_series_by_mode?.combined || {};
    const lineTarget = Array.isArray(lineSeries.target) ? lineSeries.target : [];
    const lineInstructor = Array.isArray(lineSeries.instructors?.[state.page2.instructorName]) ? lineSeries.instructors[state.page2.instructorName] : [];

    if (options.updateRoseWordcloud !== false) {
      renderChartOrFallback(containers.rose, "rose", buildRoseOption(sections, roseData));
      renderChartOrFallback(containers.wordcloud, "wordcloud", buildWordCloudOption(wordCloudData));
    }

    if (options.updateModeCharts !== false) {
      renderChartOrFallback(containers.averageBar, "average-bar", buildAverageBarOption(sections, averageSeries));
      renderChartOrFallback(containers.instructorBar, "instructor-bar", buildInstructorBarOption(sections, instructors, instructorSeries));
    }

    if (options.updateLine !== false) {
      renderChartOrFallback(containers.line, "line", buildLineOption(sections, lineTarget, lineInstructor, state.page2.instructorName));
    }
  }

  function updatePage2Charts(containers, options = {}) {
    renderPage2Charts(containers, options);
  }

  function buildRoseOption(sections, data) {
    return {
      backgroundColor: "transparent",
      tooltip: { trigger: "item" },
      legend: {
        bottom: 0,
        type: "scroll",
      },
      series: [
        {
          name: "강의 비중",
          type: "pie",
          radius: ["24%", "74%"],
          center: ["50%", "45%"],
          roseType: "radius",
          itemStyle: {
            borderRadius: 12,
            borderColor: "#fff",
            borderWidth: 2,
          },
          label: {
            color: "#23263a",
          },
          data: data.length
            ? data.map((item, index) => ({
                name: item.name || sections[index]?.title || `대주제 ${index + 1}`,
                value: Number(item.value || 0),
                itemStyle: { color: CHART_COLORS[index % CHART_COLORS.length] },
              }))
            : sections.map((section, index) => ({
                name: section.title,
                value: Number(section.target_weight || 0),
                itemStyle: { color: CHART_COLORS[index % CHART_COLORS.length] },
              })),
        },
      ],
    };
  }

  function buildWordCloudOption(data) {
    const items = data.length ? data : [{ name: "데이터 없음", value: 1 }];
    return {
      tooltip: {},
      series: [
        {
          type: "wordCloud",
          shape: "circle",
          gridSize: 8,
          sizeRange: [14, 54],
          rotationRange: [-45, 45],
          textStyle: {
            color: (params) => stableColorForKey(params?.name || params?.data?.name || params?.value || "word"),
          },
          data: items.map((item, index) => ({
            name: item.name,
            value: item.value,
            textStyle: {
              color: stableColorForKey(item.name || String(index)),
            },
          })),
        },
      ],
    };
  }

  function buildAverageBarOption(sections, seriesItems) {
    const safeItems = seriesItems.length ? seriesItems : sections.map((section) => ({
      section_id: section.id,
      section_title: section.title,
      share: Number(section.target_weight || 0) / 100,
    }));
    return {
      tooltip: { trigger: "item" },
      legend: {
        bottom: 0,
        type: "scroll",
      },
      grid: { left: 8, right: 8, top: 24, bottom: 48, containLabel: true },
      xAxis: { type: "value", max: 100, axisLabel: { formatter: "{value}%" } },
      yAxis: { type: "category", data: ["전체 평균"] },
      series: safeItems.map((item, index) => ({
        name: item.section_title || sections[index]?.title || `대주제 ${index + 1}`,
        type: "bar",
        stack: "average",
        barWidth: 22,
        data: [Math.round((item.share || 0) * 10000) / 100],
        itemStyle: { color: CHART_COLORS[index % CHART_COLORS.length] },
      })),
    };
  }

  function buildInstructorBarOption(sections, instructors, seriesByInstructor) {
    return {
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      legend: {
        bottom: 0,
        type: "scroll",
      },
      grid: { left: 16, right: 16, top: 24, bottom: 56, containLabel: true },
      xAxis: { type: "value", max: 100, axisLabel: { formatter: "{value}%" } },
      yAxis: {
        type: "category",
        data: instructors.map((item) => item.name),
      },
      series: sections.map((section, index) => ({
        name: section.title,
        type: "bar",
        stack: "instructors",
        barWidth: 16,
        data: instructors.map((instructor) => {
          const series = seriesByInstructor[instructor.name] || [];
          const item = series.find((entry) => entry.section_id === section.id);
          return Math.round((item?.share || 0) * 10000) / 100;
        }),
        itemStyle: { color: CHART_COLORS[index % CHART_COLORS.length] },
      })),
    };
  }

  function buildLineOption(sections, target, instructor, instructorName) {
    const labels = sections.map((item) => item.title);
    const targetValues = labels.map((_, index) => Math.round((target[index]?.share || 0) * 10000) / 100);
    const instructorValues = labels.map((_, index) => Math.round((instructor[index]?.share || 0) * 10000) / 100);
    const instructorColor = stableColorForKey(instructorName || "selected-instructor");
    return {
      tooltip: { trigger: "axis" },
      legend: { bottom: 0 },
      grid: { left: 20, right: 20, top: 24, bottom: 52, containLabel: true },
      xAxis: { type: "category", data: labels },
      yAxis: { type: "value", max: 100, axisLabel: { formatter: "{value}%" } },
      series: [
        {
          name: "목표",
          type: "line",
          smooth: true,
          data: targetValues,
          lineStyle: { width: 3, color: CHART_COLORS[0] },
          itemStyle: { color: CHART_COLORS[0] },
        },
        {
          name: instructorName || "선택 강사",
          type: "line",
          smooth: true,
          data: instructorValues,
          lineStyle: { width: 3, color: instructorColor },
          itemStyle: { color: instructorColor },
        },
      ],
    };
  }

  function renderChartOrFallback(container, kind, option) {
    if (!container) {
      return;
    }
    if (window.echarts && typeof window.echarts.init === "function") {
      try {
        const instance = state.page2.charts.get(container) || window.echarts.init(container);
        instance.setOption(option, true);
        state.page2.charts.set(container, instance);
        return;
      } catch (error) {
        // Fall through to a simple readable fallback if a chart type is unavailable.
        container.innerHTML = "";
      }
    }

    renderFallbackVisual(container, kind, option);
  }

  function renderFallbackVisual(container, kind, option) {
    container.innerHTML = "";
    const wrapper = document.createElement("div");
    wrapper.className = "chart-fallback";
    if (kind === "wordcloud") {
      const items = option.series?.[0]?.data || [];
      items.slice(0, 20).forEach((item) => {
        const chip = document.createElement("span");
        chip.className = "chart-fallback-chip";
        chip.textContent = item.name;
        chip.style.fontSize = `${Math.max(12, Math.min(30, 12 + Number(item.value || 0) * 1.5))}px`;
        wrapper.appendChild(chip);
      });
    } else if (kind === "rose") {
      const items = option.series?.[0]?.data || [];
      items.forEach((item) => {
        const row = document.createElement("div");
        row.className = "chart-fallback-row";
        row.textContent = `${item.name}: ${Number(item.value || 0).toFixed(1)}%`;
        wrapper.appendChild(row);
      });
    } else if (kind === "line") {
      const series = option.series || [];
      series.forEach((item) => {
        const row = document.createElement("div");
        row.className = "chart-fallback-row";
        row.textContent = `${item.name}: ${(item.data || []).map((value) => Number(value || 0).toFixed(1)).join(" · ")}`;
        wrapper.appendChild(row);
      });
    } else {
      const series = option.series || [];
      series.forEach((item) => {
        const row = document.createElement("div");
        row.className = "chart-fallback-row";
        row.textContent = `${item.name}: ${(item.data || []).map((value) => Number(value || 0).toFixed(1)).join(" · ")}`;
        wrapper.appendChild(row);
      });
    }
    container.appendChild(wrapper);
  }

  function resizeCharts() {
    state.page2.charts.forEach((instance) => {
      if (instance && typeof instance.resize === "function") {
        instance.resize();
      }
    });
  }

  function renderInsights(root, result) {
    root.innerHTML = "";
    const cards = Array.isArray(result.insights) ? result.insights : [];
    cards.forEach((card, index) => {
      const article = document.createElement("article");
      article.className = "insight-card";
      article.dataset.insightCard = String(index);
      article.innerHTML = `
        <div class="insight-card-head">
          <span class="insight-icon" aria-hidden="true">${iconSvg(card.icon)}</span>
          <div>
            <h3>${escapeHtml(card.title || `인사이트 ${index + 1}`)}</h3>
            <p>${escapeHtml(card.category || "insight")}</p>
          </div>
        </div>
        <p class="insight-issue">${escapeHtml(card.issue || "")}</p>
        <p class="insight-evidence">${escapeHtml(card.evidence || "")}</p>
        <p class="insight-recommendation">${escapeHtml(card.recommendation || "")}</p>
      `;
      root.appendChild(article);
    });
    const trendMeta = trendStatusMeta(result.external_trends_status);
    const footer = document.createElement("div");
    footer.className = `trend-status ${trendMeta.className}`;
    footer.textContent = trendMeta.message;
    root.appendChild(footer);
  }

  function trendStatusMeta(status) {
    const normalized = String(status || "").trim().toLowerCase();
    if (normalized === "planned" || normalized === "pending") {
      return {
        className: "is-planned",
        message: "외부 동향 인사이트는 아직 준비 중입니다.",
      };
    }
    if (normalized === "reflected" || normalized === "completed" || normalized === "ready") {
      return {
        className: "is-success",
        message: "외부 동향 인사이트가 결과에 반영되었습니다.",
      };
    }
    if (normalized === "failed" || normalized === "insufficient" || normalized === "unavailable") {
      return {
        className: "is-failed",
        message: "외부 동향을 충분히 수집하지 못해 내부 분석만 표시합니다.",
      };
    }
    return {
      className: "is-unknown",
      message: "외부 동향 상태를 확인 중입니다.",
    };
  }

  function iconSvg(name) {
    const normalized = String(name || "").trim().toLowerCase();
    if (normalized === "target") {
      return `
        <svg viewBox="0 0 24 24" role="img" focusable="false">
          <path d="M12 4v16M4 12h16M7.5 7.5l9 9M16.5 7.5l-9 9" />
          <circle cx="12" cy="12" r="6" />
          <circle cx="12" cy="12" r="2.5" />
        </svg>
      `;
    }
    if (normalized === "users") {
      return `
        <svg viewBox="0 0 24 24" role="img" focusable="false">
          <path d="M16.5 19a4.5 4.5 0 0 0-9 0M9.5 9.5a2.5 2.5 0 1 0 0-.01M18.5 18a3.5 3.5 0 0 0-2.7-3.4M15.5 8.5a2 2 0 1 1 0-.01" />
        </svg>
      `;
    }
    if (normalized === "spark") {
      return `
        <svg viewBox="0 0 24 24" role="img" focusable="false">
          <path d="m12 3 1.8 4.2L18 9l-4.2 1.8L12 15l-1.8-4.2L6 9l4.2-1.8L12 3Zm6 11 1 2.4L21 17l-2 1-1 2.5-1-2.5-2-1 2-.6 1-2.4ZM5.5 13l.8 1.8L8 15.5l-1.7.7-.8 1.8-.8-1.8L3 15.5l1.7-.7.8-1.8Z" />
        </svg>
      `;
    }
    if (normalized === "refresh") {
      return `
        <svg viewBox="0 0 24 24" role="img" focusable="false">
          <path d="M20 11a8 8 0 1 1-2.3-5.7M20 4v5h-5" />
        </svg>
      `;
    }
    if (normalized === "lightbulb") {
      return `
        <svg viewBox="0 0 24 24" role="img" focusable="false">
          <path d="M9 18h6M10 21h4M8.5 14.5c-1.6-1.2-2.5-3.1-2.5-5.2a6 6 0 1 1 12 0c0 2.1-.9 4-2.5 5.2-.8.7-1.3 1.5-1.5 2.5h-4c-.2-1-.7-1.8-1.5-2.5Z" />
        </svg>
      `;
    }
    if (normalized === "trend") {
      return `
        <svg viewBox="0 0 24 24" role="img" focusable="false">
          <path d="M5 17 10 12l3 3 6-7M5 6v11h14" />
        </svg>
      `;
    }
    return `
      <svg viewBox="0 0 24 24" role="img" focusable="false">
        <path d="M12 3v18M3 12h18" />
      </svg>
    `;
  }

  function bindDialog(surface, openSelectors, closeSelectors, onOpen) {
    if (!surface) {
      return;
    }
    qsa(joinSelectors(openSelectors)).forEach((button) => {
      button.addEventListener("click", (event) => {
        event.preventDefault();
        openSurface(surface);
        if (onOpen) {
          onOpen();
        }
      });
    });
    qsa(joinSelectors(closeSelectors)).forEach((button) => {
      button.addEventListener("click", () => closeSurface(surface));
    });
    surface.addEventListener("click", (event) => {
      if (event.target === surface) {
        closeSurface(surface);
      }
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && isOpen(surface)) {
        closeSurface(surface);
      }
    });
  }

  function bindPanel(surface, openSelectors, closeSelectors) {
    if (!surface) {
      return;
    }
    qsa(joinSelectors(openSelectors)).forEach((button) => {
      button.addEventListener("click", (event) => {
        event.preventDefault();
        toggleSurface(surface);
      });
    });
    qsa(joinSelectors(closeSelectors)).forEach((button) => {
      button.addEventListener("click", () => closeSurface(surface));
    });
    surface.addEventListener("click", (event) => {
      if (event.target === surface) {
        closeSurface(surface);
      }
    });
  }

  function openSurface(surface) {
    surface.hidden = false;
    surface.classList.add(CSS.open);
    surface.setAttribute("aria-hidden", "false");
  }

  function closeSurface(surface) {
    surface.hidden = true;
    surface.classList.remove(CSS.open);
    surface.setAttribute("aria-hidden", "true");
  }

  function toggleSurface(surface) {
    if (isOpen(surface)) {
      closeSurface(surface);
    } else {
      openSurface(surface);
    }
  }

  function isOpen(surface) {
    return !surface.hidden && surface.classList.contains(CSS.open);
  }

  function syncModeButtons(buttons) {
    buttons.forEach((button) => {
      const mode = normalizeMode(button.getAttribute("data-view-mode") || button.getAttribute("data-mode-toggle") || button.getAttribute("data-page2-mode"));
      const active = mode === state.page2.mode;
      button.classList.toggle(CSS.selected, active);
      button.classList.toggle(CSS.active, active);
      button.setAttribute("aria-pressed", String(active));
      button.title = button.title || mode;
    });
  }

  function syncInstructorButtons(buttons, selectedIndex, selectedName) {
    buttons.forEach((button) => {
      const index = Number(button.getAttribute("data-instructor-index"));
      let active = Number.isInteger(index) && index === selectedIndex;
      if (!active) {
        const name = button.getAttribute("data-instructor-name") || button.getAttribute("data-instructor-id") || button.textContent?.trim();
        active = Boolean(selectedName && name === selectedName);
      }
      button.classList.toggle(CSS.selected, active);
      button.classList.toggle(CSS.active, active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function selectPage2Instructor(target, containers, options = {}) {
    const result = state.page2.result;
    const instructors = Array.isArray(result?.instructors) ? result.instructors : [];
    if (!instructors.length) {
      return;
    }
    const nextIndex = resolveInstructorIndex(target, state.page2.instructorIndex);
    state.page2.instructorIndex = nextIndex;
    state.page2.instructorName = instructors[nextIndex]?.name || instructors[0].name;
    updatePage2Charts(containers, options);
  }

  function getSelectedInstructorRecord(instructors) {
    if (!instructors.length) {
      return { instructor: null, index: 0 };
    }
    const index = resolveInstructorIndex(state.page2.instructorIndex || state.page2.instructorName, 0);
    return {
      instructor: instructors[index] || instructors[0],
      index,
    };
  }

  function resolveInstructorIndex(value, fallbackIndex = 0) {
    const result = state.page2.result;
    const instructors = Array.isArray(result?.instructors) ? result.instructors : [];
    if (!instructors.length) {
      return 0;
    }
    const numeric = Number(value);
    if (Number.isInteger(numeric)) {
      return wrapIndex(numeric, instructors.length);
    }
    const name = String(value || "").trim();
    if (name) {
      const matchedIndex = instructors.findIndex((item) => item.name === name);
      if (matchedIndex >= 0) {
        return matchedIndex;
      }
    }
    return wrapIndex(fallbackIndex, instructors.length);
  }

  function wrapIndex(index, length) {
    if (!length) {
      return 0;
    }
    return ((index % length) + length) % length;
  }

  function stableColorForKey(key) {
    const value = String(key || "");
    if (!value) {
      return CHART_COLORS[0];
    }
    let hash = 0;
    for (let index = 0; index < value.length; index += 1) {
      hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
    }
    const palette = CHART_COLORS.slice(1);
    if (!palette.length) {
      return CHART_COLORS[0];
    }
    return palette[hash % palette.length];
  }

  function setTextForTargets(targets, value) {
    (Array.isArray(targets) ? targets : []).forEach((target) => {
      if (target) {
        target.textContent = value;
      }
    });
  }

  function normalizeMode(mode) {
    const value = String(mode || "").toLowerCase();
    if (value.includes("speech") || value.includes("발화")) {
      return "speech";
    }
    if (value.includes("material") || value.includes("자료")) {
      return "material";
    }
    return "combined";
  }

  function fetchCourses() {
    return fetchJson("/courses", { method: "GET" })
      .then((payload) => (Array.isArray(payload.courses) ? payload.courses : []))
      .catch(() => []);
  }

  function fetchJson(url, options) {
    return fetch(url, options).then(async (response) => {
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = payload.detail || payload.message || response.statusText || "요청 실패";
        throw new Error(detail);
      }
      return payload;
    });
  }

  function ensureRenderedContainer(surface, name, fallbackTag) {
    let container = surface.querySelector(`[data-role='${name}']`);
    if (!container) {
      container = surface.querySelector(`[data-${name}]`);
    }
    if (!container) {
      container = document.createElement(fallbackTag || "div");
      container.dataset.role = name;
      surface.appendChild(container);
    }
    return container;
  }

  function ensureHiddenInput(form, name) {
    if (!form) {
      return null;
    }
    let input = form.querySelector(`input[type='hidden'][name='${name}']`);
    if (!input) {
      input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      form.appendChild(input);
    }
    return input;
  }

  function setFieldValue(node, value) {
    if (!node) {
      return;
    }
    if ("value" in node) {
      node.value = value;
    } else {
      node.textContent = value;
    }
  }

  function valueOf(node) {
    if (!node) {
      return "";
    }
    if ("value" in node) {
      return node.value || "";
    }
    return node.textContent || "";
  }

  function setStatus(node, message) {
    if (!node) {
      return;
    }
    node.textContent = message;
  }

  function setBusy(button, busy, label) {
    if (!button) {
      return;
    }
    button.disabled = busy;
    if (label) {
      button.dataset.busyLabel = label;
      if (busy) {
        button.dataset.originalLabel = button.dataset.originalLabel || button.textContent || "";
        button.textContent = label;
      } else if (button.dataset.originalLabel) {
        button.textContent = button.dataset.originalLabel;
      }
    }
  }

  function setButtonDisabled(button, disabled) {
    if (button) {
      button.disabled = disabled;
    }
  }

  function courseSaveButton() {
    return $(SELECTORS.courseSaveButton);
  }

  function summaryPreviewWeights(sections) {
    const total = sections.reduce((sum, section) => sum + Number(section.target_weight || 0), 0);
    return `${Math.round(total * 10) / 10}%`;
  }

  function normalizePreview(payload) {
    const sections = Array.isArray(payload.sections) ? payload.sections.map((section, index) => ({
      id: section.id || uniqueId(`section-${index + 1}`),
      title: section.title || `섹션 ${index + 1}`,
      description: section.description || section.title || "",
      target_weight: Number(section.target_weight || 0),
    })) : [];
    return {
      raw_curriculum_text: payload.raw_curriculum_text || "",
      sections,
      warnings: Array.isArray(payload.warnings) ? payload.warnings : [],
    };
  }

  function renderCoursePreviewTable() {
    // Intentionally left as a named hook for the structure worker contract.
  }

  function findOne(root, selectors) {
    return findFirst(root, selectors);
  }

  function joinSelectors(selectors) {
    return selectors.filter(Boolean).join(", ");
  }

  function findFirst(root, selectors) {
    const scope = root && root.querySelector ? root : document;
    return scope.querySelector(joinSelectors(selectors));
  }

  function qsa(selector, root = document) {
    if (!selector) {
      return [];
    }
    return Array.from((root || document).querySelectorAll(selector));
  }

  function $(selector, root = document) {
    return (root || document).querySelector(selector);
  }

  function text(node) {
    return node ? node.textContent || "" : "";
  }

  function safeParseJSON(raw, fallback) {
    if (!raw) {
      return fallback;
    }
    try {
      return JSON.parse(raw);
    } catch {
      return fallback;
    }
  }

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function escapeAttr(value) {
    return escapeHtml(value).replaceAll("`", "&#96;");
  }

  function iconLabel(name) {
    const key = String(name || "").toLowerCase();
    const map = {
      target: "🎯",
      users: "👥",
      spark: "✨",
      refresh: "🔁",
      lightbulb: "💡",
    };
    return map[key] || "💡";
  }

  function uniqueId(prefix) {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return `${prefix}-${window.crypto.randomUUID().slice(0, 8)}`;
    }
    return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
  }

  function debounce(fn, delay) {
    let timer = null;
    return (...args) => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => fn(...args), delay);
    };
  }

  function updateCourseListSelectionWhenRendered() {
    updateCourseListSelection($(SELECTORS.courseListPanel));
  }

  window.addEventListener("load", updateCourseListSelectionWhenRendered);
})();
